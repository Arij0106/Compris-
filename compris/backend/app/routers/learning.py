"""GET /quiz · POST /answer · POST /evaluate · GET /profile · GET /review · POST /review/grade"""
import random
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Attempt, Chapter, Concept, Course, Question, ReviewCard
from app.schemas import AnswerIn, EvaluateIn, ReviewGradeIn
from app.services import knowledge_tracing as kt
from app.services import retrieval, risk, selection, tutor
from app.services.questions import _fallback_questions
from app.services.spaced import apply_sm2

router = APIRouter(tags=["learning"])


def _public_question(q: Question, concept_name: str) -> dict:
    level_map = {
        "remember": "Retenir",
        "understand": "Comprendre",
        "apply": "Appliquer",
        "analyze": "Analyser",
        "evaluate": "Évaluer",
        "create": "Créer",
    }
    level = level_map.get(str(q.bloom_level).lower(), "Comprendre")
    return {
        "id": str(q.id),
        "question": q.text,
        "text": q.text,
        "choices": q.choices,
        "concept": concept_name,
        "concept_id": q.concept_id,
        "level": level,
        "bloom_level": q.bloom_level,
        "difficulty": q.difficulty,
    }


def _resolve_course_id(db: Session, course_id: str | int | None) -> int | None:
    if course_id is not None:
        try:
            return int(str(course_id).split(",")[0].strip())
        except ValueError:
            pass
    latest = db.scalar(select(Course).order_by(Course.id.desc()).limit(1))
    return latest.id if latest else None


@router.get("/quiz")
def quiz(
    course_id: str | int | None = None,
    unit_id: str | int | None = None,
    concept_id: int | None = None,
    student_id: str | None = None,
    n: int = Query(5, ge=1, le=30),
    db: Session = Depends(get_db),
):
    cid = _resolve_course_id(db, course_id)
    if cid is None:
        return {"questions": [], "questions_status": "error"}
    course = db.get(Course, cid)
    if not course:
        raise HTTPException(404, "Cours introuvable")

    if student_id:
        kt.get_student(db, student_id)
        db.commit()

    # Si unit_id est passé, identifier les concepts de cette unité (chapitre)
    target_concept_ids = set()
    if unit_id is not None:
        try:
            uid_int = int(str(unit_id).strip())
            # Vérifier si c'est un chapitre
            ch = db.get(Chapter, uid_int)
            if ch:
                for c in db.scalars(select(Concept).where(Concept.chapter_id == ch.id)).all():
                    target_concept_ids.add(c.id)
            else:
                # Peut-être directement un concept
                target_concept_ids.add(uid_int)
        except ValueError:
            pass

    if concept_id:
        target_concept_ids.add(concept_id)

    # Récupération des questions
    all_course_concepts = db.scalars(select(Concept).where(Concept.course_id == cid)).all()
    names = {c.id: c.name for c in all_course_concepts}

    # Fix #6 : exclure les questions superficielles à trous ("Complétez", "_____")
    q_query = select(Question).where(
        Question.course_id == cid,
        ~Question.text.like("%Complétez%"),
        ~Question.text.like("%____%"),
    )
    if target_concept_ids:
        q_query = q_query.where(Question.concept_id.in_(target_concept_ids))

    # Fix #2 : ordonner aléatoirement pour que les questions changent à chaque re-tentative / analyse
    # Prioriser les questions pas encore tentées par l'étudiant
    all_matching_qs = db.scalars(q_query).all()
    if student_id:
        attempted_qids = set(
            db.scalars(
                select(Attempt.question_id).where(Attempt.student_id == student_id, Attempt.course_id == cid)
            ).all()
        )
        unseen_qs = [q for q in all_matching_qs if q.id not in attempted_qids]
        seen_qs = [q for q in all_matching_qs if q.id in attempted_qids]
        random.shuffle(unseen_qs)
        random.shuffle(seen_qs)
        qs = (unseen_qs + seen_qs)[:n]
    else:
        random.shuffle(all_matching_qs)
        qs = all_matching_qs[:n]

    # Si pas assez de questions pédagogiques en base pour cette unité, en générer immédiatement avec variété
    if len(qs) < n and all_course_concepts:
        chosen_concepts = [c for c in all_course_concepts if not target_concept_ids or c.id in target_concept_ids]
        if not chosen_concepts:
            chosen_concepts = all_course_concepts[:3]
        all_names = [c.name for c in all_course_concepts]

        needed_more = n - len(qs)
        for c in chosen_concepts:
            if needed_more <= 0:
                break
            ctx = retrieval.search(db, cid, f"{c.name}. {c.description}", k=3)
            fallback = _fallback_questions(c, ctx, all_names, 2)
            for fq in fallback:
                new_q = Question(course_id=cid, concept_id=c.id, **fq)
                db.add(new_q)
                db.flush()
                qs.append(new_q)
                needed_more -= 1
                if needed_more <= 0:
                    break
        if qs:
            db.commit()

    return {
        "questions": [_public_question(q, names.get(q.concept_id, "Concept")) for q in qs[:n]],
        "questions_status": course.questions_status,
    }


@router.post("/evaluate")
def evaluate(body: EvaluateIn, db: Session = Depends(get_db)):
    """Évalue les réponses à un quiz d'unité et renvoie l'analyse détaillée des lacunes."""
    student_id = body.student_id or "student_1"
    kt.get_student(db, student_id)

    feedback = []
    gaps = []
    seen_gap_concepts = set()
    score = 0
    course_id = None

    for item in body.answers:
        try:
            qid = int(str(item.question_id).strip())
        except ValueError:
            continue
        q = db.get(Question, qid)
        if not q:
            continue

        course_id = q.course_id
        concept = db.get(Concept, q.concept_id)
        concept_name = concept.name if concept else "Concept clé"
        is_correct = (item.answer == q.correct_index)

        if is_correct:
            score += 1
            expl = q.explanation or "Excellente réponse !"
        else:
            # Fix #11 : ne PAS donner directement la bonne réponse brute.
            # Fournir un indice pédagogique et guider vers la bonne page pour que l'étudiant trouve lui-même.
            expl = (
                f"Indice de révision : Votre réponse n'est pas tout à fait exacte. "
                f"Repensez à la propriété essentielle de « {concept_name} » (page {q.source_page or 1} du cours). "
                "Analysez le fonctionnement de cette notion pour identifier vous-même la bonne proposition !"
            )
            if concept_name not in seen_gap_concepts:
                seen_gap_concepts.add(concept_name)
                gaps.append({
                    "concept": concept_name,
                    "explanation": f"Notion à approfondir : revoir « {concept_name} » (page {q.source_page or 1}).",
                })

        # Enregistrer l'essai et mettre à jour le Knowledge Tracing (BKT)
        db.add(
            Attempt(
                student_id=student_id,
                course_id=q.course_id,
                concept_id=q.concept_id,
                question_id=q.id,
                correct=is_correct,
                time_spent=10.0,
            )
        )
        kt.record_answer(db, student_id, q.concept_id, is_correct)

        feedback.append({
            "question_id": str(q.id),
            "correct": is_correct,
            "explanation": expl,
        })

    db.commit()
    total = len(body.answers) if body.answers else len(feedback)
    acquired = (score >= 2 and total <= 3) or (score / total >= 0.67 if total > 0 else True)

    # Fix #7 : générer une synthèse du chapitre lorsque l'étudiant réussit le quiz
    synthesis = None
    if acquired and course_id:
        course = db.get(Course, course_id)
        lang = course.language if course else "fr"
        synthesis = tutor.chapter_synthesis(db, course_id, body.unit_id, lang)

    return {
        "score": score,
        "total": total,
        "acquired": acquired,
        "gaps": gaps,
        "feedback": feedback,
        "synthesis": synthesis,
    }


@router.post("/answer")
def answer(body: AnswerIn, db: Session = Depends(get_db)):
    q = db.get(Question, body.question_id)
    if not q:
        raise HTTPException(404, "Question introuvable")
    kt.get_student(db, body.student_id)
    correct = body.choice_index == q.correct_index

    db.add(
        Attempt(
            student_id=body.student_id, course_id=q.course_id, concept_id=q.concept_id,
            question_id=q.id, correct=correct, time_spent=body.time_spent,
        )
    )
    kt.record_answer(db, body.student_id, q.concept_id, correct)

    card = db.scalar(select(ReviewCard).where(ReviewCard.student_id == body.student_id, ReviewCard.question_id == q.id))
    if card is None:
        card = ReviewCard(
            student_id=body.student_id, course_id=q.course_id, concept_id=q.concept_id, question_id=q.id,
            front=q.text, back=f"{q.choices[q.correct_index]}\n\n{q.explanation}".strip(), due_date=date.today(),
        )
        db.add(card)
    apply_sm2(card, 4 if correct else 1)

    db.flush()
    answered = {a for (a,) in db.execute(select(Attempt.question_id).where(Attempt.student_id == body.student_id, Attempt.course_id == q.course_id))}
    nxt = selection.select_questions(db, q.course_id, body.student_id, None, 1, exclude=answered | {q.id})
    cids = [c for (c,) in db.execute(select(Concept.id).where(Concept.course_id == q.course_id))]
    mastery = kt.mastery_map(db, body.student_id, cids)
    db.commit()
    return {
        "correct": correct,
        "correct_index": q.correct_index,
        "explanation": q.explanation,
        "next_question_id": nxt[0].id if nxt else None,
        "mastery": {str(k): v for k, v in mastery.items()},
    }


@router.get("/profile")
def profile(student_id: str, course_id: int | None = None, db: Session = Depends(get_db)):
    if course_id is not None:
        if not db.get(Course, course_id):
            raise HTTPException(404, "Cours introuvable")
    else:
        course_id = db.scalar(select(Attempt.course_id).where(Attempt.student_id == student_id).order_by(Attempt.id.desc()).limit(1))
    if course_id is None:
        return {"concepts": [], "global_risk": "medium", "global_risk_score": 0.5, "features": {}}
    concepts = db.scalars(select(Concept).where(Concept.course_id == course_id).order_by(Concept.id)).all()
    ids = [c.id for c in concepts]
    mastery = kt.mastery_map(db, student_id, ids)
    attempts_by = {}
    for a in db.scalars(select(Attempt).where(Attempt.student_id == student_id, Attempt.course_id == course_id)):
        attempts_by[a.concept_id] = attempts_by.get(a.concept_id, 0) + 1
    by_id = {c.id: c for c in concepts}

    out = []
    for c in concepts:
        att = attempts_by.get(c.id, 0)
        pre = [(by_id[p].name, mastery.get(p, 0), attempts_by.get(p, 0)) for p in (c.prerequisites or []) if p in by_id]
        out.append(
            {
                "id": c.id, "name": c.name, "mastery": mastery.get(c.id, 0.3), "attempts": att,
                "risk": selection.risk_of(mastery.get(c.id, 0.3), att),
                "recommendation": selection.recommendation(c, mastery.get(c.id, 0.3), att, pre),
            }
        )
    attempted = [x["mastery"] for x in out if x["attempts"] > 0]
    avg_mastery = sum(attempted) / len(attempted) if attempted else 0.0
    feats = risk.student_features(db, student_id, course_id)
    score, level = risk.predict(feats, avg_mastery)
    return {"concepts": out, "global_risk": level, "global_risk_score": score, "features": feats}


@router.get("/review")
def review(student_id: str, course_id: int | None = None, include_future: bool = False, db: Session = Depends(get_db)):
    q = select(ReviewCard).where(ReviewCard.student_id == student_id)
    if course_id is not None:
        q = q.where(ReviewCard.course_id == course_id)
    if not include_future:
        q = q.where(ReviewCard.due_date <= date.today())
    cards = db.scalars(q.order_by(ReviewCard.due_date)).all()
    names = {c.id: c.name for c in db.scalars(select(Concept).where(Concept.id.in_({k.concept_id for k in cards})))} if cards else {}
    return {
        "cards": [
            {"id": c.id, "front": c.front, "back": c.back, "due_date": c.due_date.isoformat(),
             "concept": names.get(c.concept_id, ""), "interval_days": c.interval_days}
            for c in cards
        ]
    }


@router.post("/review/grade")
def review_grade(body: ReviewGradeIn, db: Session = Depends(get_db)):
    card = db.get(ReviewCard, body.card_id)
    if not card or card.student_id != body.student_id:
        raise HTTPException(404, "Carte introuvable")
    apply_sm2(card, body.quality)
    db.commit()
    return {"card_id": card.id, "next_due_date": card.due_date.isoformat(), "interval_days": card.interval_days}


@router.get("/profile")
def profile(student_id: str, course_id: int | None = None, db: Session = Depends(get_db)):
    if course_id is not None:
        if not db.get(Course, course_id):
            raise HTTPException(404, "Cours introuvable")
    else:  # par défaut : le dernier cours sur lequel l'étudiant a travaillé
        course_id = db.scalar(select(Attempt.course_id).where(Attempt.student_id == student_id).order_by(Attempt.id.desc()).limit(1))
    if course_id is None:
        return {"concepts": [], "global_risk": "medium", "global_risk_score": 0.5, "features": {}}
    concepts = db.scalars(select(Concept).where(Concept.course_id == course_id).order_by(Concept.id)).all()
    ids = [c.id for c in concepts]
    mastery = kt.mastery_map(db, student_id, ids)
    attempts_by = {}
    for a in db.scalars(select(Attempt).where(Attempt.student_id == student_id, Attempt.course_id == course_id)):
        attempts_by[a.concept_id] = attempts_by.get(a.concept_id, 0) + 1
    by_id = {c.id: c for c in concepts}

    out = []
    for c in concepts:
        att = attempts_by.get(c.id, 0)
        pre = [(by_id[p].name, mastery.get(p, 0), attempts_by.get(p, 0)) for p in (c.prerequisites or []) if p in by_id]
        out.append(
            {
                "id": c.id, "name": c.name, "mastery": mastery.get(c.id, 0.3), "attempts": att,
                "risk": selection.risk_of(mastery.get(c.id, 0.3), att),
                "recommendation": selection.recommendation(c, mastery.get(c.id, 0.3), att, pre),
            }
        )
    attempted = [x["mastery"] for x in out if x["attempts"] > 0]
    avg_mastery = sum(attempted) / len(attempted) if attempted else 0.0
    feats = risk.student_features(db, student_id, course_id)
    score, level = risk.predict(feats, avg_mastery)
    return {"concepts": out, "global_risk": level, "global_risk_score": score, "features": feats}


@router.get("/review")
def review(student_id: str, course_id: int | None = None, include_future: bool = False, db: Session = Depends(get_db)):
    q = select(ReviewCard).where(ReviewCard.student_id == student_id)
    if course_id is not None:
        q = q.where(ReviewCard.course_id == course_id)
    if not include_future:
        q = q.where(ReviewCard.due_date <= date.today())
    cards = db.scalars(q.order_by(ReviewCard.due_date)).all()
    names = {c.id: c.name for c in db.scalars(select(Concept).where(Concept.id.in_({k.concept_id for k in cards})))} if cards else {}
    return {
        "cards": [
            {"id": c.id, "front": c.front, "back": c.back, "due_date": c.due_date.isoformat(),
             "concept": names.get(c.concept_id, ""), "interval_days": c.interval_days}
            for c in cards
        ]
    }


@router.post("/review/grade")
def review_grade(body: ReviewGradeIn, db: Session = Depends(get_db)):
    card = db.get(ReviewCard, body.card_id)
    if not card or card.student_id != body.student_id:
        raise HTTPException(404, "Carte introuvable")
    apply_sm2(card, body.quality)
    db.commit()
    return {"card_id": card.id, "next_due_date": card.due_date.isoformat(), "interval_days": card.interval_days}
