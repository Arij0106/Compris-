"""Génération de la banque de questions (niveaux de Bloom + difficulté)."""
import logging
import random
import re

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Concept, Course, Question
from app.services import llm, retrieval
from app.services.text import clean, sentences

log = logging.getLogger(__name__)
BLOOM_LEVELS = {"remember", "understand", "apply", "analyze", "evaluate", "create"}
BLOOM_DIFFICULTY = {"remember": 0.2, "understand": 0.35, "apply": 0.5, "analyze": 0.65, "evaluate": 0.8, "create": 0.9}


def _is_pedagogical_question(text: str, choices: list[str]) -> bool:
    """Fix #6 : rejette strictement les devinettes de lettres ('Trans...port'), textes à trous ou choix incomplets."""
    t_clean = text.strip()
    if len(t_clean) < 15:
        return False
    # Détection de trous, tirets bas multiples, points de suspension excessifs ou consignes de remplissage
    if re.search(r"(\.{3,}|_{2,}|complétez|completez|\btermi(?:ner|nez)\b|manquante?s?)", t_clean, re.IGNORECASE):
        return False
    if len(choices) != 4:
        return False
    for c in choices:
        c_clean = str(c).strip()
        if len(c_clean) < 2 or re.search(r"(\.{3,}|_{2,})", c_clean):
            return False
    # Vérifier que les 4 choix sont distincts
    if len({c.lower().strip() for c in choices}) < 4:
        return False
    return True


def _llm_questions(concept: Concept, context: list[dict], language: str, n: int) -> list[dict] | None:
    if not context:
        return None
    ctx = "\n\n".join(f"[page {c['page']}] {c['text']}" for c in context)
    system = (
        "Tu es un concepteur d'évaluations universitaires et pédagogiques de haut niveau. "
        f"Tu écris des QCM à 4 choix, basés UNIQUEMENT sur les extraits du cours fournis, dans la langue du cours ({language}).\n"
        "RÈGLE STRICTE ABSOLUE : Ne formule JAMAIS de devinettes de lettres, de syllabes manquantes, de mots coupés ou de textes à trous superficiels (ex: 'Trans...port' interdit). "
        "Formule de véritables questions d'évaluation conceptuelle : compréhension du rôle, définition, comparaison ou mise en situation. "
        "Chaque choix doit être une proposition complète et intelligible. "
        "Une seule réponse correcte, 3 distracteurs plausibles et pédagogiques."
    )
    user = (
        f"Concept clé : {concept.name}\nDescription : {concept.description}\n\nExtraits du cours :\n{ctx}\n\n"
        f"Écris {n} questions conceptuelles. Format JSON : "
        '[{"text": "Énoncé clair de la question...", "choices": ["Choix A complet", "Choix B complet", "Choix C complet", "Choix D complet"], "correct_index": 0, '
        '"explanation": "Explication pédagogique avec renvoi au cours", "bloom_level": "remember|understand|apply|analyze|evaluate|create", '
        '"page": numéro_de_page}]'
    )
    data = llm.complete_json(system, user, max_tokens=2500)
    if not isinstance(data, list):
        return None
    out = []
    for d in data:
        try:
            choices = [str(c).strip() for c in d["choices"]]
            ci = int(d["correct_index"])
            text = str(d["text"]).strip()
            if not _is_pedagogical_question(text, choices) or not 0 <= ci <= 3:
                continue
            bloom = str(d.get("bloom_level", "understand")).lower()
            bloom = bloom if bloom in BLOOM_LEVELS else "understand"
            out.append(
                {
                    "text": text,
                    "choices": choices,
                    "correct_index": ci,
                    "explanation": str(d.get("explanation", "")).strip(),
                    "bloom_level": bloom,
                    "difficulty": BLOOM_DIFFICULTY[bloom],
                    "source_page": d.get("page") if isinstance(d.get("page"), int) else context[0]["page"],
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out or None


def _fallback_questions(concept: Concept, context: list[dict], all_names: list[str], n: int) -> list[dict]:
    """Sans LLM : questions conceptuelles structurées (QCM de compréhension, variées à chaque génération)."""
    # Fix #2 : générateur aléatoire dynamique pour varier les questions à chaque analyse
    rng = random.Random()
    others = [x for x in all_names if x.lower() != concept.name.lower()]
    if len(others) < 3:
        others = others + [f"Notion annexe {i}" for i in range(1, 4)]

    # Collecte des phrases riches du cours (filtrées pour exclure les trous)
    all_sents = []
    for c in context:
        for s in sentences(c.get("text", "")):
            s_clean = clean(s)
            if 40 <= len(s_clean) <= 280 and not re.search(r"(\.{3,}|_{2,})", s_clean):
                all_sents.append((s_clean, c.get("page", 1)))

    # Mélanger pour varier les phrases sources
    rng.shuffle(all_sents)

    out = []
    concept_pattern = re.compile(r"\b" + re.escape(concept.name.lower()) + r"\b", re.IGNORECASE)

    # 1. Questions de compréhension basées sur les phrases du cours
    matching_sents = [(s, p) for s, p in all_sents if concept_pattern.search(s)]
    non_matching = [s for s, _ in all_sents if not concept_pattern.search(s)]
    rng.shuffle(matching_sents)
    rng.shuffle(non_matching)

    for s, page in matching_sents:
        if len(out) >= n:
            break
        if len(non_matching) >= 3:
            distractors = rng.sample(non_matching, 3)
        else:
            distractors = [
                f"Cette propriété s'applique uniquement à des traitements sans rapport avec {concept.name}.",
                f"Il s'agit d'une convention secondaire sans incidence sur les principes de base.",
                f"Cette notion est désactivée par défaut dans la configuration standard.",
            ]
        choices = [s] + distractors
        rng.shuffle(choices)
        correct_idx = choices.index(s)
        q_text = f"D'après le cours, quelle affirmation caractérise fidèlement la notion de « {concept.name} » ?"
        if _is_pedagogical_question(q_text, choices):
            out.append(
                {
                    "text": q_text,
                    "choices": choices,
                    "correct_index": correct_idx,
                    "explanation": f"D'après le cours (page {page}) : « {s} »",
                    "bloom_level": "understand",
                    "difficulty": BLOOM_DIFFICULTY["understand"],
                    "source_page": page,
                }
            )

    # 2. Questions de définition / identification de concept
    if len(out) < n and concept.description and len(concept.description) > 15:
        concept_choices = rng.sample(others, min(3, len(others))) + [concept.name]
        rng.shuffle(concept_choices)
        page = context[0]["page"] if context else 1
        q_text = f"Quelle notion du cours correspond précisément à cette définition : « {concept.description} » ?"
        if _is_pedagogical_question(q_text, concept_choices):
            out.append(
                {
                    "text": q_text,
                    "choices": concept_choices,
                    "correct_index": concept_choices.index(concept.name),
                    "explanation": f"Il s'agit bien de « {concept.name} », définie ainsi dans le cours (page {page}).",
                    "bloom_level": "remember",
                    "difficulty": BLOOM_DIFFICULTY["remember"],
                    "source_page": page,
                }
            )

    # 3. Question sur le rôle dans le chapitre
    if len(out) < n and matching_sents:
        s, page = matching_sents[0]
        concept_choices = rng.sample(others, min(3, len(others))) + [concept.name]
        rng.shuffle(concept_choices)
        q_text = f"Dans ce chapitre, quel concept fondamental est directement associé à la propriété suivante : « {s} » ?"
        if _is_pedagogical_question(q_text, concept_choices):
            out.append(
                {
                    "text": q_text,
                    "choices": concept_choices,
                    "correct_index": concept_choices.index(concept.name),
                    "explanation": f"Cette propriété concerne directement « {concept.name} » (page {page}).",
                    "bloom_level": "analyze",
                    "difficulty": BLOOM_DIFFICULTY["analyze"],
                    "source_page": page,
                }
            )

    return out[:n]


def generate_question_bank(course_id: int) -> None:
    """Tâche de fond lancée après /upload (session DB dédiée)."""
    db = SessionLocal()
    try:
        course = db.get(Course, course_id)
        if not course:
            return
        course.questions_status = "running"
        db.commit()

        # Fix #6 : nettoyer préalablement les anciennes questions à trous ou non pédagogiques
        old_bad = db.scalars(
            select(Question).where(
                Question.course_id == course_id,
                (Question.text.like("%Complétez%")) | (Question.text.like("%____%")) | (Question.text.like("%...%"))
            )
        ).all()
        for bq in old_bad:
            db.delete(bq)
        if old_bad:
            db.commit()

        concepts = db.scalars(select(Concept).where(Concept.course_id == course_id)).all()
        names = [c.name for c in concepts]
        for concept in concepts:
            # Fix #10 : vérifier si le concept possède déjà des questions valides
            existing_count = len(db.scalars(select(Question).where(Question.concept_id == concept.id)).all())
            needed = max(0, settings.questions_per_concept - existing_count)
            if needed == 0:
                continue

            ctx = retrieval.search(db, course_id, f"{concept.name}. {concept.description}", k=3)
            qs = _llm_questions(concept, ctx, course.language, needed)
            if not qs:
                qs = _fallback_questions(concept, ctx, names, needed)
            for q in qs:
                db.add(Question(course_id=course_id, concept_id=concept.id, **q))
            db.commit()
        course.questions_status = "ready"
        db.commit()
    except Exception:
        log.exception("Échec de la génération de questions (cours %s)", course_id)
        db.rollback()
        course = db.get(Course, course_id)
        if course:
            course.questions_status = "error"
            db.commit()
    finally:
        db.close()
