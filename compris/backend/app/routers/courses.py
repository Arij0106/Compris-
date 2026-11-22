"""POST /upload  ·  POST /analyze  ·  GET /courses/{id}"""
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Chapter, Concept, Course, Question
from app.schemas import AnalyzeIn
from app.services import ingestion, retrieval
from app.services.questions import generate_question_bank

router = APIRouter(tags=["courses"])


def _course_payload(db: Session, course: Course) -> dict:
    chapters = db.scalars(select(Chapter).where(Chapter.course_id == course.id).order_by(Chapter.idx)).all()
    concepts = db.scalars(select(Concept).where(Concept.course_id == course.id).order_by(Concept.id)).all()
    return {
        "course_id": str(course.id),
        "id": course.id,
        "title": course.title,
        "chapters": [{"id": c.id, "title": c.title} for c in chapters],
        "concepts": [{"id": c.id, "name": c.name} for c in concepts],
    }


@router.post("/upload")
def upload(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    language: str = Form("fr"),
    db: Session = Depends(get_db),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ingestion.SUPPORTED:
        raise HTTPException(400, f"Format non supporté ({ext or '?'}). Formats : {', '.join(sorted(ingestion.SUPPORTED))}")

    original_stem = Path(file.filename).stem if file.filename else "cours"
    course_title = title.strip() if title and title.strip() else original_stem
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename or "cours")
    path = settings.storage_dir / "uploads" / f"{uuid.uuid4().hex[:8]}_{safe}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(file.file.read())

    course = Course(title=course_title, language=language, filename=safe, status="processing")
    db.add(course)
    db.flush()
    try:
        pages = ingestion.extract_pages(path)
        ingestion.ingest_course(db, course, pages)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc))
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, f"Erreur pendant l'analyse du cours : {exc}")
    course.status = "ready"
    course.questions_status = "pending"
    db.commit()
    retrieval.invalidate(course.id)
    background.add_task(generate_question_bank, course.id)  # banque de questions générée en tâche de fond
    return {**_course_payload(db, course), "questions_status": "pending"}


@router.post("/analyze")
def analyze(body: AnalyzeIn, db: Session = Depends(get_db)):
    """Découpe les cours sélectionnés en unités d'apprentissage ordonnées hiérarchiquement."""
    cids: list[int] = []
    if body.course_ids:
        raw_ids = body.course_ids if isinstance(body.course_ids, list) else str(body.course_ids).split(",")
        for x in raw_ids:
            try:
                cids.append(int(str(x).strip()))
            except ValueError:
                pass
    elif body.course_id:
        try:
            cids.append(int(str(body.course_id).strip()))
        except ValueError:
            pass

    if not cids:
        cids = [c.id for c in db.scalars(select(Course).order_by(Course.id.asc())).all()]

    # Fix #8 : trier les cours par leur ordre hiérarchique naturel (ID / création), indépendamment de l'ordre de sélection
    courses = [db.get(Course, cid) for cid in sorted(set(cids))]
    courses = [c for c in courses if c is not None]

    units = []
    for course in courses:
        # Tri strict des chapitres par leur index hiérarchique naturel
        chapters = db.scalars(
            select(Chapter)
            .where(Chapter.course_id == course.id)
            .order_by(Chapter.idx.asc(), Chapter.page_start.asc())
        ).all()
        if chapters:
            for ch in chapters:
                units.append({
                    "id": str(ch.id),
                    "course_id": course.id,
                    "title": ch.title,
                    "idx": ch.idx,
                    "summary": f"Pages {ch.page_start} à {ch.page_end} · {course.title}",
                })
        else:
            concepts = db.scalars(
                select(Concept).where(Concept.course_id == course.id).order_by(Concept.id.asc())
            ).all()
            if concepts:
                for c in concepts:
                    units.append({
                        "id": str(c.id),
                        "course_id": course.id,
                        "title": c.name,
                        "idx": c.id,
                        "summary": c.description or f"Notion du cours {course.title}",
                    })
            else:
                units.append({
                    "id": str(course.id),
                    "course_id": course.id,
                    "title": course.title,
                    "idx": course.id,
                    "summary": f"Document complet ({course.filename})",
                })

    return {"units": units}

    return {"units": units}


@router.get("/courses")
def list_courses(db: Session = Depends(get_db)):
    rows = db.scalars(select(Course).order_by(Course.id.desc())).all()
    return {"courses": [{"course_id": c.id, "title": c.title, "status": c.status, "questions_status": c.questions_status} for c in rows]}


@router.get("/courses/{course_id}")
def get_course(course_id: int, db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Cours introuvable")
    n_q = db.scalar(select(func.count()).select_from(Question).where(Question.course_id == course_id))
    return {**_course_payload(db, course), "status": course.status, "questions_status": course.questions_status, "n_questions": n_q}
