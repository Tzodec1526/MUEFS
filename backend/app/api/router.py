from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.cases import router as cases_router
from app.api.clerk_review import router as clerk_router
from app.api.court_rules import router as court_rules_router
from app.api.courts import router as courts_router
from app.api.documents import router as documents_router
from app.api.favorites import router as favorites_router
from app.api.filings import router as filings_router
from app.api.notifications import router as notifications_router
from app.api.payments import router as payments_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(courts_router)
api_router.include_router(court_rules_router)
api_router.include_router(cases_router)
api_router.include_router(filings_router)
api_router.include_router(clerk_router)
api_router.include_router(documents_router)
api_router.include_router(favorites_router)
api_router.include_router(notifications_router)
api_router.include_router(payments_router)
api_router.include_router(admin_router)
