from app.api.routers.analysis import router as analysis_router
from app.api.routers.evaluation import router as evaluation_router
from app.api.routers.knowledge import router as knowledge_router
from app.api.routers.system import router as system_router
from app.api.routers.workflow import router as workflow_router

__all__ = [
    "analysis_router",
    "evaluation_router",
    "knowledge_router",
    "system_router",
    "workflow_router",
]
