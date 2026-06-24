from src.api.v1.events import router as events_router
from src.api.v1.auth import router as auth_router
from src.api.v1.uploads import router as uploads_router
from src.api.v1.media import router as media_router
from src.api.v1.albums import router as albums_router
from src.api.v1.downloads import router as downloads_router

__all__ = ["events_router", "auth_router", "uploads_router", "media_router", "albums_router", "downloads_router"]

