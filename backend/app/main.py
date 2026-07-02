import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import agent, audit, auth, delegations, directory, requests, templates
from app.config import get_settings
from app.db import Base, SessionLocal, engine as db_engine
from app.exceptions import DomainError
from app.services.engine import run_escalation_sweep

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("app")


async def _escalation_loop(interval_seconds: int):
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            with SessionLocal() as db:
                escalated = run_escalation_sweep(db)
                db.commit()
                if escalated:
                    logger.info("Escalated %d overdue steps", escalated)
        except Exception:
            logger.exception("Escalation sweep failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    Base.metadata.create_all(bind=db_engine)
    if settings.seed_on_startup:
        from app.seed import seed

        with SessionLocal() as db:
            seed(db)
    task = None
    if settings.enable_escalation_sweep:
        task = asyncio.create_task(_escalation_loop(settings.escalation_sweep_seconds))
    yield
    if task:
        task.cancel()


app = FastAPI(
    title="Approval Workflow Engine",
    description="Generic approval workflow engine with an agentic AI assistant (Kimi k2.6).",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/healthz", tags=["health"])
def healthz():
    return {"status": "ok"}


for router in (auth.router, directory.router, templates.router, requests.router,
               delegations.router, audit.router, agent.router):
    app.include_router(router, prefix="/api")
