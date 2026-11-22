"""Suivi de maîtrise par concept (BKT) — persistance en base."""
import json
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Mastery, Student
from app.services import bkt


@lru_cache(maxsize=1)
def get_params() -> dict:
    """Paramètres BKT globaux appris sur ASSISTments (models/bkt_params.json), sinon valeurs par défaut."""
    path = settings.models_dir / "bkt_params.json"
    if path.exists():
        try:
            return json.loads(path.read_text())["global"]
        except Exception:
            pass
    return dict(bkt.DEFAULT_PARAMS)


def reload_params() -> None:
    get_params.cache_clear()


def get_student(db: Session, student_id: str) -> Student:
    st = db.get(Student, student_id)
    if st is None:
        st = Student(id=student_id)
        db.add(st)
        db.flush()
    return st


def mastery_map(db: Session, student_id: str, concept_ids: list[int]) -> dict[int, float]:
    if not concept_ids:
        return {}
    default = get_params()["p_init"]
    rows = db.scalars(
        select(Mastery).where(Mastery.student_id == student_id, Mastery.concept_id.in_(concept_ids))
    ).all()
    known = {m.concept_id: m.p_known for m in rows}
    return {cid: round(known.get(cid, default), 4) for cid in concept_ids}


def record_answer(db: Session, student_id: str, concept_id: int, correct: bool) -> float:
    params = get_params()
    # Recherche dans la session ou la base
    m = db.get(Mastery, (student_id, concept_id))
    if m is None:
        m = db.scalar(
            select(Mastery).where(Mastery.student_id == student_id, Mastery.concept_id == concept_id)
        )
    if m is None:
        m = Mastery(student_id=student_id, concept_id=concept_id, p_known=params["p_init"], n_attempts=0)
        db.add(m)
        db.flush()
    m.p_known = bkt.update(m.p_known, correct, params)
    m.n_attempts += 1
    m.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.flush()
    return m.p_known
