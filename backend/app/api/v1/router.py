from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.service_accounts import router as service_accounts_router
from app.api.v1.questions import router as questions_router
from app.api.v1.answers import answers_router, questions_answers_router
from app.api.v1.reviews import router as reviews_router
from app.api.v1.ai_logs import router as ai_logs_router
from app.api.v1.worker_triggers import router as worker_triggers_router
from app.api.v1.source_documents import router as source_documents_router
from app.api.v1.events import router as events_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(service_accounts_router)
api_router.include_router(questions_router)
api_router.include_router(questions_answers_router)
api_router.include_router(answers_router)
api_router.include_router(reviews_router)
api_router.include_router(ai_logs_router)
api_router.include_router(worker_triggers_router)
api_router.include_router(source_documents_router)
api_router.include_router(events_router)
