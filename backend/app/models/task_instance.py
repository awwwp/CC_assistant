from datetime import date, datetime, time
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.recurrence_rule import RecurrenceRule


class TaskInstance(Base):
    """A specific occurrence of a recurring task that has been touched in
    some way (checked in, undone, or otherwise customized). Pending
    occurrences are NOT stored — they are derived at render time by
    expanding the rule's RRULE within its [dtstart, dtend] window.

    Per DESIGN.md §4.3:
      - `completed_at` is written exactly once and never modified.
      - `undone_at` is written exactly once and never modified.
      - Once `undone_at` is set, the state is terminal.
    These constraints are enforced by `TaskInstanceRepository`.
    """

    __tablename__ = "task_instances"
    __table_args__ = (
        UniqueConstraint(
            "rule_id", "occurrence_date", name="uq_task_instances_rule_date"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("recurrence_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    occurrence_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    undone_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    override_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    override_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
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

    rule: Mapped["RecurrenceRule"] = relationship(back_populates="instances")
