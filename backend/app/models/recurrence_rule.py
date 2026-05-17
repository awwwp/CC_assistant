from datetime import date, datetime, time
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.tag import Tag
    from app.models.task_instance import TaskInstance


class RecurrenceRule(Base):
    """A single revision of a recurring-task rule.

    Multiple revisions of "the same task" share a `series_id` (UUID).
    Each revision is active within [dtstart, dtend]; modifying a
    schedule-affecting field creates a new revision instead of mutating
    this one. See DESIGN.md §4.4.2.
    """

    __tablename__ = "recurrence_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rrule: Mapped[str] = mapped_column(String, nullable=False)
    dtstart: Mapped[date] = mapped_column(Date, nullable=False)
    dtend: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    time_of_day: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tag_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tags.id", ondelete="RESTRICT"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tag: Mapped[Optional["Tag"]] = relationship(lazy="selectin")
    instances: Mapped[list["TaskInstance"]] = relationship(
        back_populates="rule",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
