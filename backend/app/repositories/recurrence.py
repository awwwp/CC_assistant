import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import RecurrenceRule, TaskCompletionLog, TaskInstance
from app.schemas.recurrence import CheckinRequest, RuleCreate, RuleUpdate


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class InvalidRuleModificationError(ValueError):
    """Schedule-affecting rule modification missing or invalid effective_from."""


class TagNotFoundError(ValueError):
    """Rule references a tag that does not exist or is soft-deleted."""

    def __init__(self, tag_id: int):
        self.tag_id = tag_id
        super().__init__(f"Tag id {tag_id} not found or deleted")


class AlreadyCheckedInError(ValueError):
    def __init__(self, rule_id: int, occurrence_date: date):
        super().__init__(
            f"Instance rule={rule_id} date={occurrence_date} is already checked in"
        )


class WithdrawnInstanceError(ValueError):
    """Instance has been undone (terminal state); no further state changes allowed."""

    def __init__(self, rule_id: int, occurrence_date: date):
        super().__init__(
            f"Instance rule={rule_id} date={occurrence_date} has been undone (terminal state)"
        )


class NotCheckedInError(ValueError):
    def __init__(self, rule_id: int, occurrence_date: date):
        super().__init__(
            f"Cannot undo: instance rule={rule_id} date={occurrence_date} is not checked in"
        )


# --------------------------------------------------------------------------- #
# RecurrenceRuleRepository
# --------------------------------------------------------------------------- #


class RecurrenceRuleRepository:
    """CRUD for RecurrenceRule, enforcing the soft-delete invariant and the
    cosmetic-vs-schedule modification split (DESIGN.md §4.4.2)."""

    SCHEDULE_AFFECTING_FIELDS = frozenset(
        {"rrule", "time_of_day", "duration_minutes", "category"}
    )

    def __init__(self, db: Session):
        self.db = db

    def _base_query(self):
        return (
            select(RecurrenceRule)
            .where(RecurrenceRule.deleted_at.is_(None))
            .options(selectinload(RecurrenceRule.tag))
        )

    def list_all(self) -> list[RecurrenceRule]:
        stmt = self._base_query().order_by(RecurrenceRule.id)
        return list(self.db.scalars(stmt).all())

    def list_by_series(self, series_id: str) -> list[RecurrenceRule]:
        stmt = (
            self._base_query()
            .where(RecurrenceRule.series_id == series_id)
            .order_by(RecurrenceRule.dtstart)
        )
        return list(self.db.scalars(stmt).all())

    def get(self, rule_id: int) -> Optional[RecurrenceRule]:
        stmt = self._base_query().where(RecurrenceRule.id == rule_id)
        return self.db.scalar(stmt)

    def _verify_tag(self, tag_id: Optional[int]) -> None:
        if tag_id is None:
            return
        from app.models import Tag

        tag = self.db.scalar(
            select(Tag).where(Tag.id == tag_id, Tag.deleted_at.is_(None))
        )
        if tag is None:
            raise TagNotFoundError(tag_id)

    def create(self, data: RuleCreate) -> RecurrenceRule:
        self._verify_tag(data.tag_id)
        rule = RecurrenceRule(
            **data.model_dump(),
            series_id=str(uuid.uuid4()),
        )
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def modify(self, rule: RecurrenceRule, data: RuleUpdate) -> RecurrenceRule:
        provided = data.model_fields_set
        schedule_changes = provided & self.SCHEDULE_AFFECTING_FIELDS

        if "tag_id" in provided:
            self._verify_tag(data.tag_id)

        if schedule_changes:
            if data.effective_from is None:
                raise InvalidRuleModificationError(
                    f"effective_from is required when modifying schedule fields "
                    f"({', '.join(sorted(schedule_changes))})"
                )
            if data.effective_from <= date.today():
                raise InvalidRuleModificationError(
                    "effective_from must be strictly later than today"
                )
            return self._split_revision(rule, data)

        # Cosmetic in-place update
        updates = data.model_dump(exclude_unset=True, exclude={"effective_from"})
        for k, v in updates.items():
            setattr(rule, k, v)
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def _split_revision(
        self, old: RecurrenceRule, data: RuleUpdate
    ) -> RecurrenceRule:
        assert data.effective_from is not None  # validated by caller
        old.dtend = data.effective_from - timedelta(days=1)

        update_data = data.model_dump(
            exclude_unset=True, exclude={"effective_from"}
        )

        new_rule = RecurrenceRule(
            series_id=old.series_id,
            title=update_data.get("title", old.title),
            description=update_data.get("description", old.description),
            rrule=update_data.get("rrule", old.rrule),
            dtstart=data.effective_from,
            dtend=None,
            time_of_day=update_data.get("time_of_day", old.time_of_day),
            duration_minutes=update_data.get(
                "duration_minutes", old.duration_minutes
            ),
            category=update_data.get("category", old.category),
            tag_id=update_data.get("tag_id", old.tag_id),
            is_active=update_data.get("is_active", old.is_active),
        )
        self.db.add(new_rule)
        self.db.commit()
        self.db.refresh(new_rule)
        return new_rule

    def soft_delete(self, rule: RecurrenceRule) -> RecurrenceRule:
        rule.deleted_at = datetime.now(timezone.utc)
        today = date.today()
        if rule.dtend is None or rule.dtend > today:
            rule.dtend = today  # past still expandable, future stops
        self.db.commit()
        self.db.refresh(rule)
        return rule


# --------------------------------------------------------------------------- #
# TaskInstanceRepository
# --------------------------------------------------------------------------- #


class TaskInstanceRepository:
    """CRUD for TaskInstance, enforcing the one-shot semantics of
    `completed_at` and `undone_at` (DESIGN.md §4.3)."""

    def __init__(self, db: Session):
        self.db = db

    def get(
        self, rule_id: int, occurrence_date: date
    ) -> Optional[TaskInstance]:
        return self.db.scalar(
            select(TaskInstance).where(
                TaskInstance.rule_id == rule_id,
                TaskInstance.occurrence_date == occurrence_date,
            )
        )

    def list_for_rule(self, rule_id: int) -> list[TaskInstance]:
        return list(
            self.db.scalars(
                select(TaskInstance)
                .where(TaskInstance.rule_id == rule_id)
                .order_by(TaskInstance.occurrence_date)
            ).all()
        )

    def checkin(
        self,
        rule: RecurrenceRule,
        occurrence_date: date,
        notes: Optional[str] = None,
    ) -> TaskInstance:
        instance = self.get(rule.id, occurrence_date)

        if instance is None:
            instance = TaskInstance(
                rule_id=rule.id, occurrence_date=occurrence_date
            )
            self.db.add(instance)
        else:
            if instance.completed_at is not None:
                raise AlreadyCheckedInError(rule.id, occurrence_date)
            if instance.undone_at is not None:
                raise WithdrawnInstanceError(rule.id, occurrence_date)

        now = datetime.now(timezone.utc)
        instance.completed_at = now
        if notes is not None:
            instance.notes = notes

        log_entry = TaskCompletionLog(
            rule_id=rule.id,
            series_id=rule.series_id,
            occurrence_date=occurrence_date,
            completed_at=now,
            title_snapshot=rule.title,
            tag_color_snapshot=rule.tag.color if rule.tag else None,
            category_snapshot=rule.category,
            notes=notes,
        )
        self.db.add(log_entry)

        self.db.commit()
        self.db.refresh(instance)
        return instance

    def undo(self, rule_id: int, occurrence_date: date) -> TaskInstance:
        instance = self.get(rule_id, occurrence_date)
        if instance is None or instance.completed_at is None:
            raise NotCheckedInError(rule_id, occurrence_date)
        if instance.undone_at is not None:
            raise WithdrawnInstanceError(rule_id, occurrence_date)

        instance.undone_at = datetime.now(timezone.utc)
        # log is NOT written for undo (DESIGN.md §4.3)
        self.db.commit()
        self.db.refresh(instance)
        return instance


# --------------------------------------------------------------------------- #
# TaskCompletionLogRepository (read-only API; append happens inside checkin)
# --------------------------------------------------------------------------- #


class TaskCompletionLogRepository:
    """Read-only access to the append-only completion log. The repository
    intentionally does not expose `update` or `delete` operations."""

    def __init__(self, db: Session):
        self.db = db

    def list_in_range(
        self, start: date, end: date
    ) -> list[TaskCompletionLog]:
        stmt = (
            select(TaskCompletionLog)
            .where(TaskCompletionLog.occurrence_date.between(start, end))
            .order_by(
                TaskCompletionLog.occurrence_date.desc(),
                TaskCompletionLog.completed_at.desc(),
            )
        )
        return list(self.db.scalars(stmt).all())

    def list_by_series(self, series_id: str) -> list[TaskCompletionLog]:
        stmt = (
            select(TaskCompletionLog)
            .where(TaskCompletionLog.series_id == series_id)
            .order_by(TaskCompletionLog.occurrence_date.desc())
        )
        return list(self.db.scalars(stmt).all())
