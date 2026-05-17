from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import get_db
from app.repositories import (
    AlreadyCheckedInError,
    InvalidRuleModificationError,
    NotCheckedInError,
    RecurrenceRuleRepository,
    TagNotFoundError,
    TaskInstanceRepository,
    WithdrawnInstanceError,
)
from app.schemas import (
    CheckinRequest,
    RuleCreate,
    RuleRead,
    RuleUpdate,
    TaskInstanceRead,
)

router = APIRouter(prefix="/api/rules", tags=["recurrence"])


# --------------------------------------------------------------------------- #
# Rule CRUD
# --------------------------------------------------------------------------- #


@router.get("", response_model=list[RuleRead])
def list_rules(db: Session = Depends(get_db)):
    return RecurrenceRuleRepository(db).list_all()


@router.post("", response_model=RuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(data: RuleCreate, db: Session = Depends(get_db)):
    repo = RecurrenceRuleRepository(db)
    try:
        return repo.create(data)
    except TagNotFoundError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{rule_id}", response_model=RuleRead)
def get_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = RecurrenceRuleRepository(db).get(rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return rule


@router.get("/series/{series_id}", response_model=list[RuleRead])
def list_rule_revisions(series_id: str, db: Session = Depends(get_db)):
    """List all revisions (versions) of a rule series, ordered by `dtstart`.

    Useful for showing the history of how a recurring task evolved.
    """
    return RecurrenceRuleRepository(db).list_by_series(series_id)


@router.patch("/{rule_id}", response_model=RuleRead)
def modify_rule(rule_id: int, data: RuleUpdate, db: Session = Depends(get_db)):
    """Modify a rule. If only cosmetic fields change, updates in place; if
    any schedule-affecting field (rrule, time_of_day, duration_minutes,
    category) is touched, splits into a new revision starting at
    `effective_from` (which must be > today). Returns the affected rule —
    the original one for cosmetic updates, the new revision for splits.
    """
    repo = RecurrenceRuleRepository(db)
    rule = repo.get(rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rule not found")
    try:
        return repo.modify(rule, data)
    except InvalidRuleModificationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except TagNotFoundError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    repo = RecurrenceRuleRepository(db)
    rule = repo.get(rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rule not found")
    repo.soft_delete(rule)


# --------------------------------------------------------------------------- #
# Task instance operations (nested under rule)
# --------------------------------------------------------------------------- #


@router.get("/{rule_id}/instances", response_model=list[TaskInstanceRead])
def list_rule_instances(rule_id: int, db: Session = Depends(get_db)):
    """List all stored instances for a rule. Note: only stored instances are
    returned — pending occurrences derived from the RRULE are surfaced by
    the calendar render endpoint (slice 4)."""
    rule = RecurrenceRuleRepository(db).get(rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return TaskInstanceRepository(db).list_for_rule(rule_id)


@router.post(
    "/{rule_id}/instances/{occurrence_date}/checkin",
    response_model=TaskInstanceRead,
    status_code=status.HTTP_201_CREATED,
)
def checkin_instance(
    rule_id: int,
    occurrence_date: date,
    data: CheckinRequest = CheckinRequest(),
    db: Session = Depends(get_db),
):
    rule_repo = RecurrenceRuleRepository(db)
    rule = rule_repo.get(rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rule not found")
    inst_repo = TaskInstanceRepository(db)
    try:
        return inst_repo.checkin(rule, occurrence_date, notes=data.notes)
    except AlreadyCheckedInError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
    except WithdrawnInstanceError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))


@router.post(
    "/{rule_id}/instances/{occurrence_date}/undo",
    response_model=TaskInstanceRead,
)
def undo_instance(
    rule_id: int,
    occurrence_date: date,
    db: Session = Depends(get_db),
):
    """Undo a checked-in instance. This is a TERMINAL transition; the
    `undone_at` timestamp is one-shot per DESIGN.md §4.3. Requires
    confirmation in the UI before invoking."""
    if RecurrenceRuleRepository(db).get(rule_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rule not found")
    inst_repo = TaskInstanceRepository(db)
    try:
        return inst_repo.undo(rule_id, occurrence_date)
    except NotCheckedInError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
    except WithdrawnInstanceError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
