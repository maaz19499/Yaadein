from fastapi import FastAPI
from src.api.v1 import events_router, auth_router, uploads_router, media_router, albums_router, downloads_router

app = FastAPI(
    title="Yaadein API",
    description="AI-powered event photo and video sharing platform backend API",
    version="0.1.0",
)

app.include_router(events_router, prefix="/api/v1/events")
app.include_router(auth_router, prefix="/api/v1/events")
app.include_router(uploads_router, prefix="/api/v1/uploads")
app.include_router(media_router, prefix="/api/v1/media")
app.include_router(albums_router, prefix="/api/v1/events")
app.include_router(downloads_router, prefix="/api/v1")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy"}
