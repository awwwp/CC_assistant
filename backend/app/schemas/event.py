from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.tag import TagRead


class EventBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)
    start_at: datetime
    end_at: Optional[datetime] = None
    is_all_day: bool = False

    @model_validator(mode="after")
    def end_after_start(self) -> "EventBase":
        if self.end_at is not None and self.end_at < self.start_at:
            raise ValueError("end_at must be >= start_at")
        return self


class EventCreate(EventBase):
    tag_ids: list[int] = Field(default_factory=list)


class EventUpdate(BaseModel):
    """All fields optional; only those explicitly provided are applied.

    `tag_ids` is treated specially:
      - omitted (not in the request body) → tags are not modified
      - present (even as []) → tags are replaced wholesale with the new set
    """

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    is_all_day: Optional[bool] = None
    tag_ids: Optional[list[int]] = None


class EventRead(EventBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tags: list[TagRead]
    created_at: datetime
    updated_at: datetime
