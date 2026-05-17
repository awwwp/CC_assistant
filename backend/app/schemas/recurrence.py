from datetime import date, datetime, time
from typing import Literal, Optional

from dateutil.rrule import rrulestr
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.schemas.tag import TagRead


def _validate_rrule(value: str) -> str:
    """Normalize and syntactically validate an iCalendar RRULE.

    Accepts both `"FREQ=..."` and `"RRULE:FREQ=..."`; stores the form
    without the `RRULE:` prefix. Uses python-dateutil's parser to
    catch typos like `FRQE` or `BYDAY=ZZ`.
    """
    normalized = value.strip()
    if normalized.upper().startswith("RRULE:"):
        normalized = normalized[len("RRULE:") :]
    try:
        rrulestr(f"RRULE:{normalized}", dtstart=datetime(2000, 1, 1))
    except (ValueError, KeyError, AttributeError) as e:
        raise ValueError(f"Invalid RRULE: {e}")
    return normalized


# --------------------------------------------------------------------------- #
# RecurrenceRule schemas
# --------------------------------------------------------------------------- #


class RuleBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)
    rrule: str = Field(min_length=1, max_length=500)
    dtstart: date
    time_of_day: Optional[time] = None
    duration_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    category: Optional[str] = Field(default=None, max_length=50)
    tag_id: Optional[int] = None

    @field_validator("rrule")
    @classmethod
    def _validate_rrule_field(cls, v: str) -> str:
        return _validate_rrule(v)


class RuleCreate(RuleBase):
    pass


class RuleUpdate(BaseModel):
    """All fields optional. Modification semantics per DESIGN.md §4.4.2:

    - Cosmetic fields (`title`, `description`, `tag_id`, `is_active`) are
      applied in place.
    - Schedule-affecting fields (`rrule`, `time_of_day`, `duration_minutes`,
      `category`) cause a new revision: the current rule's `dtend` is set
      to `effective_from - 1 day`, and a new rule row is inserted with
      `dtstart = effective_from`, sharing the same `series_id`.
    - `effective_from` is REQUIRED whenever any schedule-affecting field is
      provided, and must be strictly > today.
    """

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)
    rrule: Optional[str] = Field(default=None, min_length=1, max_length=500)
    time_of_day: Optional[time] = None
    duration_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    category: Optional[str] = Field(default=None, max_length=50)
    tag_id: Optional[int] = None
    is_active: Optional[bool] = None
    effective_from: Optional[date] = None

    @field_validator("rrule")
    @classmethod
    def _validate_rrule_field(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return _validate_rrule(v)


class RuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: str
    title: str
    description: Optional[str]
    rrule: str
    dtstart: date
    dtend: Optional[date]
    time_of_day: Optional[time]
    duration_minutes: Optional[int]
    category: Optional[str]
    tag_id: Optional[int]
    tag: Optional[TagRead]
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# TaskInstance schemas
# --------------------------------------------------------------------------- #


TaskInstanceStatus = Literal["pending", "completed", "withdrawn"]


class CheckinRequest(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=10000)


class TaskInstanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int
    occurrence_date: date
    completed_at: Optional[datetime]
    undone_at: Optional[datetime]
    notes: Optional[str]
    override_title: Optional[str]
    override_time: Optional[time]
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> TaskInstanceStatus:
        if self.completed_at is None:
            return "pending"
        if self.undone_at is None:
            return "completed"
        return "withdrawn"


# --------------------------------------------------------------------------- #
# TaskCompletionLog schemas
# --------------------------------------------------------------------------- #


class CompletionLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int
    series_id: str
    occurrence_date: date
    completed_at: datetime
    title_snapshot: str
    tag_color_snapshot: Optional[str]
    category_snapshot: Optional[str]
    notes: Optional[str]
