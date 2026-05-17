from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Event, Tag
from app.schemas.event import EventCreate, EventUpdate


class TagsNotFoundError(ValueError):
    """Raised when EventCreate / EventUpdate references tag ids that do not
    exist or are soft-deleted."""

    def __init__(self, missing_ids: list[int]):
        self.missing_ids = missing_ids
        super().__init__(f"Tag IDs not found or deleted: {sorted(missing_ids)}")


class EventRepository:
    """Repository for Event. Enforces soft-delete: reads exclude rows where
    deleted_at IS NOT NULL; deletes set deleted_at instead of DELETE."""

    def __init__(self, db: Session):
        self.db = db

    def _base_query(self):
        return (
            select(Event)
            .where(Event.deleted_at.is_(None))
            .options(selectinload(Event.tags))
        )

    def list_all(self) -> list[Event]:
        stmt = self._base_query().order_by(Event.start_at)
        return list(self.db.scalars(stmt).all())

    def list_in_range(self, start: datetime, end: datetime) -> list[Event]:
        """Events whose own time window [start_at, end_at or start_at] overlaps
        the query window [start, end]."""
        stmt = (
            self._base_query()
            .where(
                and_(
                    Event.start_at <= end,
                    or_(Event.end_at.is_(None), Event.end_at >= start),
                )
            )
            .order_by(Event.start_at)
        )
        return list(self.db.scalars(stmt).all())

    def get(self, event_id: int) -> Optional[Event]:
        stmt = self._base_query().where(Event.id == event_id)
        return self.db.scalar(stmt)

    def _resolve_tags(self, tag_ids: list[int]) -> list[Tag]:
        if not tag_ids:
            return []
        unique_ids = list(dict.fromkeys(tag_ids))
        stmt = select(Tag).where(
            Tag.id.in_(unique_ids), Tag.deleted_at.is_(None)
        )
        tags = list(self.db.scalars(stmt).all())
        missing = set(unique_ids) - {t.id for t in tags}
        if missing:
            raise TagsNotFoundError(list(missing))
        return tags

    def create(self, data: EventCreate) -> Event:
        event_fields = data.model_dump(exclude={"tag_ids"})
        event = Event(**event_fields)
        event.tags = self._resolve_tags(data.tag_ids)
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def update(self, event: Event, data: EventUpdate) -> Event:
        provided = data.model_fields_set
        scalar_updates = data.model_dump(
            exclude_unset=True, exclude={"tag_ids"}
        )
        for field, value in scalar_updates.items():
            setattr(event, field, value)
        if "tag_ids" in provided:
            event.tags = self._resolve_tags(data.tag_ids or [])
        self.db.commit()
        self.db.refresh(event)
        return event

    def soft_delete(self, event: Event) -> Event:
        event.deleted_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(event)
        return event
