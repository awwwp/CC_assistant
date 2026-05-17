from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.deps import get_db
from app.repositories import EventRepository, TagsNotFoundError
from app.schemas import EventCreate, EventRead, EventUpdate

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=list[EventRead])
def list_events(
    start: Optional[datetime] = Query(
        default=None,
        description="Range start (inclusive, ISO 8601 UTC). Must be paired with `end`.",
    ),
    end: Optional[datetime] = Query(
        default=None,
        description="Range end (inclusive, ISO 8601 UTC). Must be paired with `start`.",
    ),
    db: Session = Depends(get_db),
):
    repo = EventRepository(db)
    if start is not None and end is not None:
        if start > end:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="start must be <= end",
            )
        return repo.list_in_range(start, end)
    if start is not None or end is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Provide both `start` and `end`, or neither.",
        )
    return repo.list_all()


@router.post("", response_model=EventRead, status_code=status.HTTP_201_CREATED)
def create_event(data: EventCreate, db: Session = Depends(get_db)):
    repo = EventRepository(db)
    try:
        return repo.create(data)
    except TagsNotFoundError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{event_id}", response_model=EventRead)
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = EventRepository(db).get(event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


@router.patch("/{event_id}", response_model=EventRead)
def update_event(
    event_id: int, data: EventUpdate, db: Session = Depends(get_db)
):
    repo = EventRepository(db)
    event = repo.get(event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Event not found")
    try:
        return repo.update(event, data)
    except TagsNotFoundError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, db: Session = Depends(get_db)):
    repo = EventRepository(db)
    event = repo.get(event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Event not found")
    repo.soft_delete(event)
