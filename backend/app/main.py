from fastapi import FastAPI

from app.config import settings
from app.routers import calendar, completion_log, events, rules, tags

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.include_router(tags.router)
app.include_router(events.router)
app.include_router(rules.router)
app.include_router(completion_log.router)
app.include_router(calendar.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
