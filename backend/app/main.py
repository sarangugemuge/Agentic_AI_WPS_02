"""
SkillSync Backend — FastAPI Application Entry Point
"""
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import SkillSyncException
from app.api.routes import assessments, repositories, skills, webhooks, system, job_profiles, events, gaps

# ── Logging Configuration ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO if settings.is_development else logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("skillsync")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on startup."""
    logger.info("Starting SkillSync API service...")
    await init_db()
    logger.info("Database initialized successfully.")
    yield
    logger.info("Shutting down SkillSync API service.")


app = FastAPI(
    title="SkillSync API",
    description=(
        "AI-powered skill assessment platform coordinating GitHub repository inspection "
        "and job description matching to produce evidence-backed skill findings."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "System", "description": "Operational health checks and version information"},
        {"name": "Repositories", "description": "GitHub repository registration, validation, and listing"},
        {"name": "Job Profiles", "description": "Job description ingestion and skill requirement extraction"},
        {"name": "Assessments", "description": "Assessment execution pipeline, score results, and history"},
        {"name": "Skills", "description": "Skill finding citations and code evidence inspection"},
        {"name": "Webhooks", "description": "Automated push reassessment webhook handlers"},
    ],
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from fastapi.encoders import jsonable_encoder


# ── Global Exception Handlers ────────────────────────────────────────────────
@app.exception_handler(SkillSyncException)
async def skillsync_exception_handler(request: Request, exc: SkillSyncException):
    """Handle all application-specific domain exceptions."""
    logger.warning(f"Handled application exception [{exc.error_code}]: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "status_code": exc.status_code,
            "details": jsonable_encoder(exc.details) if exc.details else None,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Format request validation errors consistently with descriptive field messages."""
    errors = jsonable_encoder(exc.errors())
    logger.warning(f"Request validation failure on {request.url.path}: {errors}")
    messages = []
    for err in exc.errors():
        msg = err.get("msg", "")
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        loc_parts = [str(l) for l in err.get("loc", []) if l not in ("body",)]
        loc_str = ".".join(loc_parts)
        messages.append(f"{loc_str}: {msg}" if loc_str else msg)
    combined_detail = "; ".join(messages) if messages else "Request validation failed. Check parameter formats and required fields."

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": combined_detail,
            "error_code": "VALIDATION_ERROR",
            "status_code": 422,
            "details": errors,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions."""
    import traceback
    tb = traceback.format_exc()
    logger.error(f"Unhandled server error on {request.url.path}: {str(exc)}\n{tb}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": f"{type(exc).__name__}: {str(exc)}",
            "traceback": tb.splitlines()[-6:],
            "error_code": "INTERNAL_SERVER_ERROR",
            "status_code": 500,
        },
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(system.router, prefix="/api", tags=["System"])
app.include_router(repositories.router, prefix="/api", tags=["Repositories"])
app.include_router(job_profiles.router, prefix="/api", tags=["Job Profiles"])
app.include_router(assessments.router, prefix="/api", tags=["Assessments"])
app.include_router(skills.router, prefix="/api", tags=["Skills"])
app.include_router(webhooks.router, prefix="/api", tags=["Webhooks"])
app.include_router(events.router, prefix="/api", tags=["Events"])
app.include_router(gaps.router, prefix="/api", tags=["Gap Solver"])
