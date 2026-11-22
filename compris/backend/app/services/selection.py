"""Sélection adaptative des questions (diagnostic) et recommandations."""
import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Attempt, Concept, Question
from app.services import knowledge_tracing as kt


def select_questions(
    db: Session,
    course_id: int,
    student_id: str | None,
    concept_id: int | None = None,
    n: int = 8,
    exclude: set[int] | None = None,
) -> list[Question]:
    """Priorise les concepts faibles, une difficulté proche du niveau de l'étudiant, et les questions pas encore vues."""
    exclude = exclude or set()
    q = select(Question).where(Question.course_id == course_id)
    if concept_id is not None:
        q = q.where(Question.concept_id == concept_id)
    questions = [x for x in db.scalars(q).all() if x.id not in exclude]
    if not questions:
        return []
    cids = list({x.concept_id for x in questions})
    mastery = kt.mastery_map(db, student_id, cids) if student_id else {c: 0.3 for c in cids}
    seen: dict[int, int] = {}
    if student_id:
        for a in db.scalars(select(Attempt).where(Attempt.student_id == student_id, Attempt.course_id == course_id)):
            seen[a.question_id] = seen.get(a.question_id, 0) + 1
    rng = random.Random()

    def score(x: Question) -> float:
        m = mastery.get(x.concept_id, 0.3)
        # concepts faibles d'abord + difficulté ≈ maîtrise + pénalité si déjà vue + un peu d'aléa
        return m + 0.6 * abs(x.difficulty - m) + 0.5 * seen.get(x.id, 0) + rng.random() * 0.15

    questions.sort(key=score)
    picked, per_concept = [], {}
    for x in questions:  # max 2 questions par concept pour couvrir large
        if per_concept.get(x.concept_id, 0) < 2:
            picked.append(x)
            per_concept[x.concept_id] = per_concept.get(x.concept_id, 0) + 1
        if len(picked) >= n:
            break
    for x in questions:  # complète si pas assez de concepts
        if len(picked) >= n:
            break
        if x not in picked:
            picked.append(x)
    return picked


def risk_of(mastery: float, attempts: int) -> str:
    if attempts == 0:
        return "medium"
    if mastery < 0.4:
        return "high"
    if mastery < 0.7:
        return "medium"
    return "low"


def recommendation(concept: Concept, mastery: float, attempts: int, prereq_status: list[tuple[str, float, int]]) -> str:
    """prereq_status : [(nom, maîtrise, nb_tentatives)] pour chaque prérequis."""
    if attempts == 0:
        return "Pas encore évalué : passe le quiz de diagnostic sur ce concept."
    weak = [name for name, m, a in prereq_status if a > 0 and m < 0.5]
    if mastery < 0.5 and weak:
        return f"Revois d'abord « {weak[0]} » (prérequis), puis reviens à ce concept."
    if mastery < 0.4:
        return "Concept fragile : demande des indices au tuteur puis refais le quiz."
    if mastery < 0.7:
        return "En bonne voie : consolide avec les cartes de révision et un quiz de niveau supérieur."
    return "Concept maîtrisé : garde le rythme avec la révision espacée."
