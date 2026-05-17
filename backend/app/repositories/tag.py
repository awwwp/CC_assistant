from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Tag
from app.schemas.tag import TagCreate, TagUpdate


class TagRepository:
    """Repository for Tag. Enforces the soft-delete invariant: reads exclude
    deleted rows; deletes set deleted_at instead of issuing DELETE."""

    def __init__(self, db: Session):
        self.db = db

    def list_active(self) -> list[Tag]:
        stmt = select(Tag).where(Tag.deleted_at.is_(None)).order_by(Tag.id)
        return list(self.db.scalars(stmt).all())

    def get(self, tag_id: int) -> Optional[Tag]:
        stmt = select(Tag).where(Tag.id == tag_id, Tag.deleted_at.is_(None))
        return self.db.scalar(stmt)

    def get_by_name(self, name: str) -> Optional[Tag]:
        stmt = select(Tag).where(Tag.name == name, Tag.deleted_at.is_(None))
        return self.db.scalar(stmt)

    def create(self, data: TagCreate) -> Tag:
        tag = Tag(**data.model_dump())
        self.db.add(tag)
        self.db.commit()
        self.db.refresh(tag)
        return tag

    def update(self, tag: Tag, data: TagUpdate) -> Tag:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(tag, field, value)
        self.db.commit()
        self.db.refresh(tag)
        return tag

    def soft_delete(self, tag: Tag) -> Tag:
        tag.deleted_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(tag)
        return tag
