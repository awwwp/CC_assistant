from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class TagBase(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    color: str = Field(pattern=HEX_COLOR_PATTERN)
    icon: Optional[str] = Field(default=None, max_length=50)
    description: Optional[str] = Field(default=None, max_length=200)


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    color: Optional[str] = Field(default=None, pattern=HEX_COLOR_PATTERN)
    icon: Optional[str] = Field(default=None, max_length=50)
    description: Optional[str] = Field(default=None, max_length=200)


class TagRead(TagBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
