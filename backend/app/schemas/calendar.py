from datetime import date, datetime, time
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field

from app.schemas.tag import TagRead

# Status of a single recurring-task occurrence on the calendar.
CalendarTaskStatus = Literal["pending", "completed", "withdrawn"]


class EventCalendarItem(BaseModel):
    """A one-shot event placed under its UTC start date.

    Multi-day events appear ONCE in the response (under start_at's date);
    the frontend uses `start_at` / `end_at` to render the visual span.
    """

    type: Literal["event"] = "event"
    id: int
    title: str
    description: Optional[str] = None
    start_at: datetime
    end_at: Optional[datetime] = None
    is_all_day: bool
    tags: list[TagRead] = Field(default_factory=list)


class TaskCalendarItem(BaseModel):
    """A single occurrence of a recurring task, derived from RRULE expansion
    and joined with the optional `task_instances` row to surface state.

    `instance_id` is null when the occurrence has never been touched (no row
    in task_instances); the frontend uses its absence as a signal that a
    `POST .../checkin` call will create the row.
    """

    type: Literal["task"] = "task"
    rule_id: int
    series_id: str
    occurrence_date: date
    title: str
    rrule: str
    time_of_day: Optional[time] = None
    duration_minutes: Optional[int] = None
    category: Optional[str] = None
    tag: Optional[TagRead] = None
    status: CalendarTaskStatus
    completed_at: Optional[datetime] = None
    undone_at: Optional[datetime] = None
    notes: Optional[str] = None
    instance_id: Optional[int] = None


CalendarItem = Annotated[
    Union[EventCalendarItem, TaskCalendarItem],
    Field(discriminator="type"),
]


class CalendarResponse(BaseModel):
    """Per-day grouping of calendar items in [start, end]. Days with no items
    are omitted from `days`; clients should default to an empty list when a
    key is missing rather than assuming an error.
    """

    start: date
    end: date
    days: dict[str, list[CalendarItem]]
