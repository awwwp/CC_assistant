from fastapi import FastAPI

from app.config import settings
from app.routers import events, tags

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.include_router(tags.router)
app.include_router(events.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
