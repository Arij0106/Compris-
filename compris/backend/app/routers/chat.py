"""POST /chat — tuteur socratique avec RAG, politesse exemplaire et réorientation vers le cours."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chapter, ChatLog, Concept, Course
from app.config import settings
from app.schemas import ChatIn
from app.services import knowledge_tracing as kt
from app.services import llm, retrieval, tutor

router = APIRouter(tags=["chat"])


def _resolve_course(db: Session, body: ChatIn) -> Course | None:
    # 1. Direct course_id
    if body.course_id is not None:
        try:
            cid = int(str(body.course_id).split(",")[0].strip())
            c = db.get(Course, cid)
            if c:
                return c
        except ValueError:
            pass

    # 2. course_ids (liste ou chaîne)
    if body.course_ids:
        raw_ids = body.course_ids if isinstance(body.course_ids, list) else str(body.course_ids).split(",")
        for item in raw_ids:
            try:
                cid = int(str(item).strip())
                c = db.get(Course, cid)
                if c:
                    return c
            except ValueError:
                continue

    # 3. Dernier cours disponible par défaut
    return db.scalar(select(Course).order_by(Course.id.desc()).limit(1))


@router.post("/chat")
def chat(body: ChatIn, db: Session = Depends(get_db)):
    course = _resolve_course(db, body)
    if not course:
        # Aucun cours importé pour le moment : réponse polie et directrice
        return {
            "reply": (
                "Bonjour ! Je suis votre tuteur pédagogique. Pour commencer à travailler ensemble, "
                "veuillez d'abord importer un cours (au format PDF, PPTX ou texte) dans le panneau de gauche."
            ),
            "sources": [],
            "type": "off_topic",
        }

    student_id = body.student_id or "student_1"
    kt.get_student(db, student_id)

    # Récupération des chapitres et concepts du cours pour contextualiser la réponse
    chapters = db.scalars(select(Chapter).where(Chapter.course_id == course.id).order_by(Chapter.idx)).all()
    concepts = db.scalars(select(Concept).where(Concept.course_id == course.id).order_by(Concept.id)).all()
    chapter_names = [c.title for c in chapters] or [c.name for c in concepts]

    history = [
        {"role": h.role, "content": h.get_text()}
        for h in body.history
    ]
    extra: dict = {}
    sources: list = []

    # Mode « assistant spécialisé » : le LLM juge lui-même si la question relève de la matière
    smart = not settings.is_socratic and llm.is_enabled() and body.mode != "feynman"

    # 1. Gestion des salutations polies
    if tutor.is_greeting(body.message):
        kind = "in_course"
        reply = tutor.greeting_reply(course.title, chapter_names, course.language)

    # 2. Gestion des remerciements
    elif tutor.is_gratitude(body.message):
        kind = "in_course"
        reply = tutor.gratitude_reply(course.language)

    # 3. Gestion des questions sans rapport avec les études (déclinées poliment)
    elif not smart and tutor.is_explicitly_non_study(body.message):
        kind = "off_topic"
        reply = tutor.polite_decline_reply(course.title, chapter_names, course.language)

    # 4. Question sur le cours / études
    elif smart:
        results = retrieval.search(db, course.id, body.message, k=6)
        unit_chunks = tutor.unit_context(db, course.id, body.unit_id)
        context = tutor._merge_context(unit_chunks, results)
        reply, off_topic, used_llm = tutor.answer_reply(
            course.title, context, body.message, history, course.language, chapter_names, body.hint_level
        )
        if off_topic:
            kind, sources = "off_topic", []
        else:
            in_course = bool(unit_chunks) or (bool(results) and results[0]["score"] >= settings.in_course_threshold)
            kind = "in_course" if in_course else "out_of_course"
            sources = tutor._sources(context) if in_course else []

    else:
        results = retrieval.search(db, course.id, body.message, k=4)
        kind = tutor.classify(results, body.message)

        if kind == "off_topic":
            reply = tutor.polite_decline_reply(course.title, chapter_names, course.language)
            sources = []
        elif kind == "out_of_course":
            # Fix #3 : interroger l'extérieur avec mention explicite
            # La notion n'est pas dans le cours mais c'est une question académique légitime.
            # L'agent explique à partir de ses connaissances en le signalant clairement.
            reply = tutor.external_academic_reply(body.message, history, course.language)
            sources = tutor._sources(results, 1) if results else []
        elif body.mode == "feynman":
            data = tutor.feynman_reply(results, body.message, history, course.language)
            reply, sources = data["reply"], tutor._sources(results)
            extra = {"score": data["score"], "gaps": data["gaps"]}
        else:
            reply = tutor.socratic_reply(results, body.message, history, body.hint_level, course.language, chapter_names)
            sources = tutor._sources(results)
            extra = {"next_hint_level": min(4, body.hint_level + 1)}

    db.add(ChatLog(student_id=student_id, course_id=course.id, message=body.message, reply=reply, type=kind))
    db.commit()

    return {"reply": reply, "sources": sources, "type": kind, **extra}
