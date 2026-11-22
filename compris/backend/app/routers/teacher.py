"""GET /teacher/dashboard · GET /ml/metrics · GET /health"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Attempt, Concept, Course, Mastery
from app.services import llm, risk

router = APIRouter(tags=["teacher"])


@router.get("/teacher/dashboard")
def dashboard(course_id: int, db: Session = Depends(get_db)):
    if not db.get(Course, course_id):
        raise HTTPException(404, "Cours introuvable")
    concepts = db.scalars(select(Concept).where(Concept.course_id == course_id)).all()
    ids = [c.id for c in concepts]
    rows = db.scalars(select(Mastery).where(Mastery.concept_id.in_(ids))).all() if ids else []
    per: dict[int, list[float]] = {}
    for m in rows:
        per.setdefault(m.concept_id, []).append(m.p_known)

    class_mastery = [
        {"concept": c.name, "concept_id": c.id, "avg": round(sum(per[c.id]) / len(per[c.id]), 4), "n_students": len(per[c.id])}
        for c in concepts if c.id in per
    ]
    hardest = sorted(class_mastery, key=lambda x: x["avg"])[:5]

    students = {s for (s,) in db.execute(select(Attempt.student_id).where(Attempt.course_id == course_id).distinct())}
    at_risk = 0
    for sid in students:
        feats = risk.student_features(db, sid, course_id)
        mvals = [m.p_known for m in rows if m.student_id == sid]
        _, level = risk.predict(feats, sum(mvals) / len(mvals) if mvals else 0.0)
        at_risk += level == "high"
    return {
        "class_mastery": class_mastery,
        "at_risk_count": at_risk,
        "hardest_concepts": hardest,
        "n_students": len(students),
    }


@router.get("/ml/metrics")
def ml_metrics():
    """Métriques des modèles entraînés (AUC, etc.) — à afficher dans la démo/le pitch."""
    data = risk.model_info()
    return data or {"detail": "Aucun modèle entraîné : lancez `python -m ml.train_all` (voir README)."}


@router.get("/health")
def health():
    return {
        "status": "ok",
        "llm_enabled": llm.is_enabled(),
        "llm_provider": llm.get_active_provider(),
        "llm_last_error": llm.LAST_ERROR,  # ex. "groq: HTTP 401 ..." = clé invalide
        "dropout_model": risk._load_model() is not None,
    }
