from app.routers.AuthRouter import router as auth_router
from app.routers.VideoRouter import router as video_router
from app.routers.AnalyticsRouter import router as analytics_router
from app.routers.IngestionRouter import router as ingestion_router
from app.routers.SemanticSearchRouter import router as semantic_search_router
from app.routers.ReprocessRouter import router as reprocess_router
from app.routers.AdminRouter import router as admin_router

__all__ = [
    "auth_router",
    "video_router",
    "analytics_router",
    "ingestion_router",
    "semantic_search_router",
    "reprocess_router",
    "admin_router",
]