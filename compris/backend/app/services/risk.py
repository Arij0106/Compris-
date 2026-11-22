"""Risque d'échec/décrochage.

Modèle entraîné sur OULAD (ml/train_oulad.py) avec 3 variables « sans échelle » qui ont un équivalent dans l'app :
  avg_score         <- taux de bonnes réponses (0-100)
  completion_rate   <- part des concepts du cours déjà travaillés (0-1)
  active_days_ratio <- jours actifs / jours écoulés depuis la 1re activité (fenêtre max 90 j) (0-1)
Sans modèle entraîné : heuristique de repli.
"""
import json
from datetime import date
from functools import lru_cache

import joblib
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Attempt, ChatLog, Concept


@lru_cache(maxsize=1)
def _load_model():
    path = settings.models_dir / "dropout_model.joblib"
    if path.exists():
        try:
            return joblib.load(path)
        except Exception:
            return None
    return None


def reload_model() -> None:
    _load_model.cache_clear()


def student_features(db: Session, student_id: str, course_id: int | None) -> dict:
    q = select(Attempt).where(Attempt.student_id == student_id)
    if course_id is not None:
        q = q.where(Attempt.course_id == course_id)
    attempts = db.scalars(q).all()
    n = len(attempts)
    accuracy = sum(a.correct for a in attempts) / n if n else 0.0

    n_concepts_total = db.scalar(
        select(func.count()).select_from(Concept).where(Concept.course_id == course_id)
    ) if course_id is not None else 0
    touched = len({a.concept_id for a in attempts})
    completion = min(1.0, touched / n_concepts_total) if n_concepts_total else 0.0

    days = {a.created_at.date() for a in attempts}
    cq = select(ChatLog.created_at).where(ChatLog.student_id == student_id)
    if course_id is not None:
        cq = cq.where(ChatLog.course_id == course_id)
    days |= {d.date() for d in db.scalars(cq).all()}
    if days:
        window = min(90, max(1, (date.today() - min(days)).days + 1))
        ratio = min(1.0, len(days) / window)
    else:
        ratio = 0.0
    return {
        "n_attempts": n,
        "accuracy": accuracy,
        "avg_score": accuracy * 100,
        "completion_rate": completion,
        "active_days_ratio": ratio,
    }


def level(score: float) -> str:
    if score >= settings.risk_high:
        return "high"
    if score >= settings.risk_medium:
        return "medium"
    return "low"


def predict(features: dict, avg_mastery: float) -> tuple[float, str]:
    """Retourne (score de risque 0..1, niveau low|medium|high)."""
    if features["n_attempts"] == 0:
        return 0.5, "medium"  # inconnu : on n'affirme rien
    bundle = _load_model()
    if bundle is not None:
        x = pd.DataFrame([[features[f] for f in bundle["features"]]], columns=bundle["features"])
        score = float(bundle["model"].predict_proba(x)[0][1])
    else:
        health = 0.6 * avg_mastery + 0.2 * features["completion_rate"] + 0.2 * features["active_days_ratio"]
        score = max(0.0, min(1.0, 1 - health))
    return round(score, 4), level(score)


def model_info() -> dict:
    path = settings.models_dir / "metrics.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}
