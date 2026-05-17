from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas import CalendarResponse
from app.services import CalendarService

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("", response_model=CalendarResponse)
def render_calendar(
    start: date = Query(
        ..., description="Inclusive start date (UTC, ISO 8601 YYYY-MM-DD)."
    ),
    end: date = Query(
        ..., description="Inclusive end date (UTC, ISO 8601 YYYY-MM-DD)."
    ),
    db: Session = Depends(get_db),
):
    """Materialize the calendar view for `[start, end]`.

    Combines one-shot events (placed under their UTC start date) with
    on-the-fly RRULE expansion of active recurring-task rules, joined to
    `task_instances` for status. See DESIGN.md §4.4.1 for the algorithm.

    Days with no items are omitted from the `days` dict in the response.
    """
    if start > end:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "start must be <= end"
        )
    if (end - start).days > CalendarService.MAX_RANGE_DAYS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"range too large (max {CalendarService.MAX_RANGE_DAYS} days)",
        )
    return CalendarService(db).render(start, end)
