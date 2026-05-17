from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TaskCompletionLog(Base):
    """Append-only journal of task completion actions.

    Per DESIGN.md §4.3, this table:
      - Records ONLY checkin events; undo does not write here.
      - Snapshots title / tag color / category at write time so later edits
        to the parent rule do not retroactively change diary entries.
      - Is exposed only via `append` in the repository layer; UPDATE / DELETE
        are never invoked by application code.

    `rule_id` uses ON DELETE RESTRICT so the FK cannot be silently broken;
    rules in this project are soft-deleted, so this is effectively a
    safeguard for direct DB tampering.
    """

    __tablename__ = "task_completion_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("recurrence_rules.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    series_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    occurrence_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    title_snapshot: Mapped[str] = mapped_column(String, nullable=False)
    tag_color_snapshot: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    category_snapshot: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)
