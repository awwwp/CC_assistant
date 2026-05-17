"""Calendar render service.

Materializes a per-day view by combining one-shot events with the
on-the-fly expansion of recurring-task rules (no instances are
pre-generated — see DESIGN.md §4.4.1).
"""

from collections import defaultdict
from datetime import date, datetime, time, timezone
from typing import Optional, Union

from dateutil.rrule import rrulestr
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Event, RecurrenceRule, TaskInstance
from app.schemas.calendar import (
    CalendarResponse,
    CalendarTaskStatus,
    EventCalendarItem,
    TaskCalendarItem,
)
from app.schemas.tag import TagRead


def _derive_status(inst: Optional[TaskInstance]) -> CalendarTaskStatus:
    if inst is None or inst.completed_at is None:
        return "pending"
    if inst.undone_at is None:
        return "completed"
    return "withdrawn"


def _sort_key(
    item: Union[EventCalendarItem, TaskCalendarItem],
) -> tuple[int, time]:
    """Stable in-day ordering: events first (by start time), then tasks
    (by `time_of_day`, with all-day / unset bucketed to the end)."""
    if isinstance(item, EventCalendarItem):
        when = time.min if item.is_all_day else item.start_at.time()
        return (0, when)
    return (1, item.time_of_day or time.max)


class CalendarService:
    """Per-day calendar render for a date window. Stateless beyond the
    injected `Session`; safe to construct per-request."""

    # Cap large windows to prevent pathological RRULE expansion.
    MAX_RANGE_DAYS = 366

    def __init__(self, db: Session):
        self.db = db

    def render(self, start: date, end: date) -> CalendarResponse:
        days: dict[str, list[Union[EventCalendarItem, TaskCalendarItem]]] = (
            defaultdict(list)
        )

        self._add_events(start, end, days)
        self._add_recurring(start, end, days)

        for d in days:
            days[d].sort(key=_sort_key)

        return CalendarResponse(start=start, end=end, days=dict(days))

    # ------------------------------------------------------------------ #
    # Events
    # ------------------------------------------------------------------ #

    def _add_events(
        self,
        start: date,
        end: date,
        days: dict[str, list],
    ) -> None:
        # Compare against day-bounded UTC datetimes so an event that spans
        # only part of a boundary day still qualifies.
        range_start = datetime.combine(start, time.min, tzinfo=timezone.utc)
        range_end = datetime.combine(end, time.max, tzinfo=timezone.utc)

        stmt = (
            select(Event)
            .where(Event.deleted_at.is_(None))
            .where(Event.start_at <= range_end)
            .where(or_(Event.end_at.is_(None), Event.end_at >= range_start))
            .options(selectinload(Event.tags))
            .order_by(Event.start_at)
        )

        for ev in self.db.scalars(stmt):
            # Place the event on its UTC start date. Multi-day events appear
            # once; the frontend uses end_at to render the span.
            placement = ev.start_at.date()
            if placement < start:
                # Event starts before the window but extends into it. Clip
                # placement so the item is reachable from a day key in the
                # response.
                placement = start

            item = EventCalendarItem(
                id=ev.id,
                title=ev.title,
                description=ev.description,
                start_at=ev.start_at,
                end_at=ev.end_at,
                is_all_day=ev.is_all_day,
                tags=[TagRead.model_validate(t) for t in ev.tags],
            )
            days[placement.isoformat()].append(item)

    # ------------------------------------------------------------------ #
    # Recurring tasks
    # ------------------------------------------------------------------ #

    def _add_recurring(
        self,
        start: date,
        end: date,
        days: dict[str, list],
    ) -> None:
        stmt = (
            select(RecurrenceRule)
            .where(RecurrenceRule.deleted_at.is_(None))
            .where(RecurrenceRule.is_active.is_(True))
            .where(RecurrenceRule.dtstart <= end)
            .where(
                or_(
                    RecurrenceRule.dtend.is_(None),
                    RecurrenceRule.dtend >= start,
                )
            )
            .options(selectinload(RecurrenceRule.tag))
        )

        for rule in self.db.scalars(stmt):
            window_start = max(rule.dtstart, start)
            window_end = min(rule.dtend or end, end)

            occurrences = self._expand_rule(rule, window_start, window_end)
            if not occurrences:
                continue

            instance_map = self._fetch_instance_map(rule.id, occurrences)

            tag_read = (
                TagRead.model_validate(rule.tag) if rule.tag else None
            )

            for d in occurrences:
                inst = instance_map.get(d)
                item = TaskCalendarItem(
                    rule_id=rule.id,
                    series_id=rule.series_id,
                    occurrence_date=d,
                    title=(
                        inst.override_title
                        if inst and inst.override_title
                        else rule.title
                    ),
                    rrule=rule.rrule,
                    time_of_day=(
                        inst.override_time
                        if inst and inst.override_time
                        else rule.time_of_day
                    ),
                    duration_minutes=rule.duration_minutes,
                    category=rule.category,
                    tag=tag_read,
                    status=_derive_status(inst),
                    completed_at=inst.completed_at if inst else None,
                    undone_at=inst.undone_at if inst else None,
                    notes=inst.notes if inst else None,
                    instance_id=inst.id if inst else None,
                )
                days[d.isoformat()].append(item)

    @staticmethod
    def _expand_rule(
        rule: RecurrenceRule,
        window_start: date,
        window_end: date,
    ) -> list[date]:
        anchor = datetime.combine(rule.dtstart, time.min)
        try:
            r = rrulestr(f"RRULE:{rule.rrule}", dtstart=anchor)
        except Exception:
            # Schemas validate RRULE at write time. If we still hit a parse
            # failure here (e.g. data corrupted by direct DB edit), skip the
            # rule rather than crash the whole render.
            return []

        after = datetime.combine(window_start, time.min)
        before = datetime.combine(window_end, time.max)
        return [occ.date() for occ in r.between(after, before, inc=True)]

    def _fetch_instance_map(
        self,
        rule_id: int,
        occurrences: list[date],
    ) -> dict[date, TaskInstance]:
        if not occurrences:
            return {}
        instances = self.db.scalars(
            select(TaskInstance).where(
                TaskInstance.rule_id == rule_id,
                TaskInstance.occurrence_date.in_(occurrences),
            )
        ).all()
        return {inst.occurrence_date: inst for inst in instances}
