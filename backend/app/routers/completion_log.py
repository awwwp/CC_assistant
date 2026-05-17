from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.deps import get_db
from app.repositories import TaskCompletionLogRepository
from app.schemas import CompletionLogRead

router = APIRouter(prefix="/api/completion-log", tags=["recurrence"])


@router.get("", response_model=list[CompletionLogRead])
def list_completion_log(
    start: Optional[date] = Query(
        default=None,
        description="Range start (inclusive). Must be paired with `end`.",
    ),
    end: Optional[date] = Query(
        default=None,
        description="Range end (inclusive). Must be paired with `start`.",
    ),
    series_id: Optional[str] = Query(
        default=None,
        description="Filter by series id (all revisions of one task).",
    ),
    db: Session = Depends(get_db),
):
    """Read-only access to the append-only completion journal.

    Either pass `start` + `end` (inclusive date range), or `series_id` to
    fetch all completions of a task across all revisions. Mixing both is
    currently not supported; ask for one or the other.
    """
    repo = TaskCompletionLogRepository(db)

    if series_id is not None:
        if start is not None or end is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Pass either `series_id` or `start`+`end`, not both.",
            )
        return repo.list_by_series(series_id)

    if start is None or end is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Provide both `start` and `end`, or `series_id`.",
        )
    if start > end:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="start must be <= end",
        )
    return repo.list_in_range(start, end)
