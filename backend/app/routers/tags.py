from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import get_db
from app.repositories import TagRepository
from app.schemas import TagCreate, TagRead, TagUpdate

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=list[TagRead])
def list_tags(db: Session = Depends(get_db)):
    return TagRepository(db).list_active()


@router.post("", response_model=TagRead, status_code=status.HTTP_201_CREATED)
def create_tag(data: TagCreate, db: Session = Depends(get_db)):
    repo = TagRepository(db)
    if repo.get_by_name(data.name):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Tag '{data.name}' already exists",
        )
    return repo.create(data)


@router.get("/{tag_id}", response_model=TagRead)
def get_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = TagRepository(db).get(tag_id)
    if tag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return tag


@router.patch("/{tag_id}", response_model=TagRead)
def update_tag(tag_id: int, data: TagUpdate, db: Session = Depends(get_db)):
    repo = TagRepository(db)
    tag = repo.get(tag_id)
    if tag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tag not found")
    if data.name is not None and data.name != tag.name:
        existing = repo.get_by_name(data.name)
        if existing is not None and existing.id != tag_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"Tag '{data.name}' already exists",
            )
    return repo.update(tag, data)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    repo = TagRepository(db)
    tag = repo.get(tag_id)
    if tag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tag not found")
    repo.soft_delete(tag)
