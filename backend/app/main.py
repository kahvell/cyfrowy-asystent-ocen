import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from app.api import (
    admin,
    ai,
    analytics,
    assistant,
    auth,
    employees,
    hr_functions,
    hr_partner,
    ipr,
    opening,
    reminders,
    reviews,
)
from app.config import settings
from app.db import engine, init_db
from app.models import User

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.seed import seed_demo, seed_reference

    init_db()
    with Session(engine) as session:
        seed_reference(session)  # kryteria, szkolenia, przepisy - zawsze
        if settings.seed_demo_data and session.exec(select(User)).first() is None:
            seed_demo(session)
    yield


app = FastAPI(
    title="Cyfrowy Asystent Ocen Okresowych",
    description="AI sugeruje, człowiek decyduje. Ocena okresowa wg rozporządzenia PRM z 4.04.2016 (Dz.U. 2016 poz. 470).",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth.router, employees.router, reviews.router, ai.router, ipr.router, analytics.router, assistant.router,
          reminders.router, hr_partner.router, admin.router, hr_functions.router, opening.router):
    app.include_router(r)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
