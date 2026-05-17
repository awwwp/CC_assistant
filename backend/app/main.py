from fastapi import FastAPI

from app.config import settings
from app.routers import tags

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.include_router(tags.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
