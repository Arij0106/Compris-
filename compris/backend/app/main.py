from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import chat, courses, learning, teacher

# ── Fix #1 : autoriser les fichiers volumineux (jusqu'à 200 Mo) ──────────
# Starlette / python-multipart limite par défaut chaque partie d'un upload
# multipart à 1 Mo (1 048 576 octets), ce qui bloque les fichiers > 1.2 Mo.
import starlette.formparsers
import starlette.requests

MAX_UPLOAD_SIZE = 200 * 1024 * 1024  # 200 Mo
starlette.formparsers.MultiPartParser.max_part_size = MAX_UPLOAD_SIZE
starlette.formparsers.MultiPartParser.spool_max_size = MAX_UPLOAD_SIZE
if getattr(starlette.formparsers.MultiPartParser.__init__, "__kwdefaults__", None):
    starlette.formparsers.MultiPartParser.__init__.__kwdefaults__["max_part_size"] = MAX_UPLOAD_SIZE
if getattr(starlette.requests.Request.form, "__kwdefaults__", None):
    starlette.requests.Request.form.__kwdefaults__["max_part_size"] = MAX_UPLOAD_SIZE


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Plateforme de tutorat socratique — API",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (courses.router, learning.router, chat.router, teacher.router):
    app.include_router(r)
