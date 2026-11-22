"""Tuteur socratique bienveillant (RAG + indices progressifs, garde-fous académiques, mode Feynman)."""
import re

from sqlalchemy import select

from app.config import settings
from app.services import llm, retrieval

HINT_GUIDE = {
    1: "NIVEAU 1 : ne donne PAS la réponse. Pose une question de relance bienveillante qui amène l'étudiant à identifier ce qu'il sait déjà.",
    2: "NIVEAU 2 : donne un indice plus précis (la notion clé ou la page à relire) toujours sans donner la solution brute, puis une question pour faire réfléchir.",
    3: "NIVEAU 3 : propose une ANALOGIE ou un exemple similaire (pas le même cas) qui illustre le raisonnement, puis invite l'étudiant à l'appliquer à son cours.",
    4: "NIVEAU 4 : l'étudiant a épuisé les indices : donne maintenant une explication claire, complète et structurée tirée du cours, puis pose une question de vérification bienveillante.",
}

# Mots-clés de salutations
GREETINGS_PATTERN = re.compile(
    r"^(bonjour|salut|bonsoir|coucou|hello|hi|hey|yo|allo|comment vas-tu|comment tu vas|ça va|qui es-tu|tu es qui|présente-toi)[.!?\s]*$",
    re.IGNORECASE,
)

# Mots-clés de remerciements
GRATITUDE_PATTERN = re.compile(
    r"^(merci|merci beaucoup|merci bien|super merci|thanks|thank you|parfait merci|d'accord merci|c'est clair merci)[.!?\s]*$",
    re.IGNORECASE,
)

# Thèmes manifestement sans rapport avec les études
# Fix #4 : filtre élargi des questions hors-études
NON_STUDY_PATTERN = re.compile(
    r"\b(météo|weather|meteo|blague|joke|humour|"
    r"film|cinema|cinéma|série|series|netflix|disney|amazon\s*prime|"
    r"football|foot|match|fifa|ligue|champions|coupe\s+du\s+monde|"
    r"ps5|ps4|xbox|playstation|jeu\s+vidéo|jeux\s+vidéo|gaming|fortnite|gta|"
    r"minecraft|league\s+of\s+legends|call\s+of\s+duty|"
    r"cuisine|recette|pizza|restaurant|bar|bière|alcool|vin|cocktail|"
    r"voiture|moto|ferrari|bmw|mercedes|"
    r"chanson|chanteur|rappeur|rap|musique|concert|spotify|"
    r"amour|drague|séduction|seduction|copine|copain|"
    r"voyage|vacances|plage|hôtel|hotel|airbnb|"
    r"politique|élection|election|président|president|ministre|"
    r"horoscope|astrologie|signe\s+astro|"
    r"crypto|bitcoin|ethereum|nft|trading|bourse|"
    r"tiktok|instagram|snapchat|facebook|twitter|"
    r"score\s+du\s+match|résultat\s+du\s+match|qui\s+a\s+gagné|"
    r"quel\s+temps|prévisions|mariage|divorce|"
    r"célébrité|celebrite|people|gossip|potins|rumeurs)\b",
    re.IGNORECASE,
)


def is_greeting(message: str) -> bool:
    return bool(GREETINGS_PATTERN.match(message.strip()))


def is_gratitude(message: str) -> bool:
    return bool(GRATITUDE_PATTERN.match(message.strip()))


def is_explicitly_non_study(message: str) -> bool:
    return bool(NON_STUDY_PATTERN.search(message))


def polite_decline_reply(course_title: str | None = None, chapter_names: list[str] | None = None, language: str = "fr") -> str:
    """Refus courtois et chaleureux pour toute demande sans rapport avec les études, avec réorientation vers le cours."""
    chapters_str = ""
    if chapter_names:
        chapters_str = f" (par exemple : {', '.join(chapter_names[:3])})"

    if language == "en":
        return (
            "Hello! I am delighted to assist you with your learning. However, as an academic tutor, my role is strictly "
            "dedicated to supporting your studies and helping you succeed in your course. Therefore, I cannot address "
            f"requests unrelated to academic work.\n\n"
            f"Let's gladly return to your course{chapters_str}: which topic or chapter would you like to explore together today?"
        )

    return (
        "Bonjour ! C'est un réel plaisir d'échanger avec vous. Cependant, en tant que tuteur pédagogique, ma mission "
        "est exclusivement de vous accompagner dans vos études et la maîtrise de votre cours. Je ne peux donc pas répondre "
        f"aux demandes qui ne concernent pas votre apprentissage scolaire.\n\n"
        f"Revenons ensemble à votre cours avec plaisir{chapters_str} : sur quel chapitre ou concept souhaitez-vous "
        "que nous travaillions aujourd'hui ?"
    )


def greeting_reply(course_title: str | None = None, chapter_names: list[str] | None = None, language: str = "fr") -> str:
    """Accueil poli et chaleureux invitant à l'étude."""
    chapters_str = ""
    if chapter_names:
        chapters_str = f" Vous pouvez explorer les chapitres disponibles, comme : {', '.join(chapter_names[:3])}."

    if language == "en":
        return (
            "Hello and welcome! I am your academic tutor, here to guide you through your course and help you master every concept. "
            f"Feel free to ask any question or explain an idea in your own words!{chapters_str}"
        )

    return (
        "Bonjour et bienvenue ! Je suis votre tuteur pédagogique, ravi de vous accompagner dans vos révisions et votre apprentissage. "
        f"Posez-moi vos questions sur le cours ou reformulez une notion avec vos mots : je suis là pour vous guider pas à pas !{chapters_str}"
    )


def external_academic_reply(message: str, history: list[dict], language: str = "fr") -> str:
    """Explique une notion académique non présente dans le cours avec la mention obligatoire requise."""
    prefix = (
        "Le cours ne mentionne pas cette notion, mais je vais vous l'expliquer à partir de mes recherches et connaissances complémentaires :\n\n"
        if language != "en"
        else "The course does not mention this concept, but I will explain it using supplementary academic research:\n\n"
    )

    system = (
        "Tu es un tuteur pédagogique d'excellence. L'étudiant te pose une question d'études ou de compréhension "
        "théorique/scientifique qui n'est pas détaillée dans son support de cours.\n"
        f"Tu DOIS commencer ta réponse par : « {prefix.strip()} »\n"
        "Fournis ensuite une explication claire, pédagogique, structurée et encourageante (3 à 5 phrases) "
        "pour faire progresser l'étudiant dans sa culture académique."
    )
    msgs = [{"role": h.get("role", "user"), "content": h.get("content") or h.get("text", "")} for h in history[-6:]] + [
        {"role": "user", "content": message}
    ]
    out = llm.complete(system, msgs, max_tokens=700, temperature=0.4)
    if out:
        # Vérifie que la mention obligatoire est bien présente au début
        if not out.lower().startswith("le cours ne mentionne pas") and not out.lower().startswith("the course does not"):
            return prefix + out
        return out

    # Mode autonome sans LLM
    return (
        f"{prefix}Cette notion concerne un concept complémentaire à votre programme. "
        "En attendant de l'aborder en classe, retenez qu'elle s'articule généralement avec les principes fondamentaux "
        "vus dans vos chapitres. N'hésitez pas à préciser votre question ou à consulter votre enseignant pour approfondir !"
    )


def classify(results: list[dict], message: str = "") -> str:
    """Classifie l'intention : salutation, gratitude, hors études (décliné), dans le cours ou question académique externe."""
    if is_greeting(message) or is_gratitude(message):
        return "in_course"
    # Fix #4 : les questions hors-études (match, météo, jeux, etc.) sont strictement déclinées
    if is_explicitly_non_study(message):
        return "off_topic"
    top = results[0]["score"] if results else 0.0
    if top >= settings.in_course_threshold:
        return "in_course"
    # Fix #3 : si la notion n'est pas dans le cours mais qu'il s'agit d'une question d'apprentissage,
    # on autorise l'explication externe avec mention explicite
    return "out_of_course"


def chapter_synthesis(db, course_id: int, unit_id: str | int | None, language: str = "fr") -> str:
    """Fix #7 : génère une synthèse pédagogique structurée à la validation réussie d'un chapitre."""
    from sqlalchemy import select
    from app.models import Chapter, Concept, Chunk

    chapter = None
    if unit_id is not None:
        try:
            uid_int = int(str(unit_id).strip())
            chapter = db.get(Chapter, uid_int)
        except ValueError:
            pass

    if chapter:
        concepts = db.scalars(select(Concept).where(Concept.chapter_id == chapter.id)).all()
        chunks = db.scalars(select(Chunk).where(Chunk.chapter_id == chapter.id)).all()
        ch_title = chapter.title
    else:
        concepts = db.scalars(select(Concept).where(Concept.course_id == course_id)).all()
        chunks = db.scalars(select(Chunk).where(Chunk.course_id == course_id).limit(6)).all()
        ch_title = "ce chapitre"

    concept_bullets = "\n".join(f"- **{c.name}** : {c.description}" for c in concepts if c.description)
    context_text = "\n".join(c.text for c in chunks[:5])

    if llm.is_enabled():
        system = (
            "Tu es un tuteur pédagogique d'excellence. "
            "Rédige une synthèse de récapitulation claire, valorisante et structurée pour un étudiant venant de valider le quiz d'un chapitre. "
            "Résume les points essentiels et leur portée méthodologique ou théorique (3 à 5 points clés). "
            f"Langue : {language}."
        )
        user = (
            f"Chapitre : {ch_title}\n"
            f"Concepts clés :\n{concept_bullets or 'Notions du chapitre'}\n\n"
            f"Extraits du cours :\n{context_text[:3000]}\n\n"
            "Rédige la synthèse pédagogique récapitulative :"
        )
        out = llm.complete(system, [{"role": "user", "content": user}], max_tokens=700, temperature=0.3)
        if out:
            return out

    # Mode autonome sans LLM externe
    if concept_bullets:
        return (
            f"🎉 **Félicitations pour la validation de : {ch_title} !**\n\n"
            "**Synthèse des notions fondamentales de ce chapitre :**\n\n"
            f"{concept_bullets}\n\n"
            "💡 *Ces concepts sont désormais maîtrisés. Vous pouvez aborder la suite du programme avec sérénité !*"
        )
    return (
        f"🎉 **Félicitations pour la validation de : {ch_title} !**\n\n"
        "Vous avez démontré une solide compréhension des concepts essentiels de ce chapitre. "
        "Les définitions et règles fondamentales sont bien acquises pour la suite du cours."
    )


def _sources(results: list[dict], k: int = 3) -> list[dict]:
    seen, out = set(), []
    for r in results[:k]:
        key = (r["page"], r["chapter"])
        if key not in seen:
            seen.add(key)
            out.append({
                "page": r["page"],
                "chapter": r["chapter"],
                "chapitre": r["chapter"],
            })
    return out


def _context(results: list[dict]) -> str:
    return "\n\n".join(f"[Page {r['page']} — {r['chapter']}]\n{r['text']}" for r in results[:4])


def socratic_reply(
    results: list[dict],
    message: str,
    history: list[dict],
    hint_level: int,
    language: str,
    chapter_names: list[str] | None = None,
) -> str:
    system = (
        "Tu es un tuteur pédagogique socratique d'excellence : bienveillant, chaleureux, extrêmement poli, patient et méthodique.\n"
        "Ton objectif est d'aider l'étudiant à comprendre activement et en profondeur SON cours.\n\n"
        "RÈGLES STRICTES ET FONDAMENTALES :\n"
        "1) MISSION STRICTEMENT ACADÉMIQUE : Tu te consacres UNIQUEMENT à l'étude et au cours fourni. "
        "Si l'étudiant te pose une question ou te fait une demande NON LIÉE aux études ou au cours (ex. loisirs, météo, blagues, potins, jeux vidéo, cuisine, discussions générales hors cours) : "
        "décline avec la plus grande politesse et bienveillance, puis réoriente-le chaleureusement vers son cours et les notions à étudier.\n"
        "2) POLITESSE ET COURTOISIE : Sois toujours respectueux, encourageant et poli. Salue avec bienveillance si l'étudiant salue.\n"
        "3) PÉDAGOGIE SOCRATIQUE : Appuie-toi sur les extraits du cours fournis (en citant la page, ex. « p. 12 »). "
        "Ne donne JAMAIS la solution brute d'emblée : guide pas à pas selon le niveau d'indice demandé.\n"
        f"4) {HINT_GUIDE.get(hint_level, HINT_GUIDE[1])}\n"
        "5) FORMAT : Réponses concises, claires et soignées (3 à 5 phrases max), dans la langue de l'étudiant/du cours.\n\n"
        f"Langue du cours : {language}.\n\nEXTRAITS DU COURS :\n{_context(results)}"
    )
    msgs = [{"role": h.get("role", "user"), "content": h.get("content") or h.get("text", "")} for h in history[-8:]] + [
        {"role": "user", "content": message}
    ]
    out = llm.complete(system, msgs, max_tokens=600, temperature=0.4)
    if out:
        return out
    return _fallback_reply(results, message, hint_level, chapter_names, language)


def _fallback_reply(
    results: list[dict],
    message: str = "",
    hint_level: int = 1,
    chapter_names: list[str] | None = None,
    language: str = "fr",
) -> str:
    """Sans LLM externe : tuteur socratique autonome, poli et rigoureux."""
    if is_greeting(message):
        return greeting_reply(chapter_names=chapter_names, language=language)
    if is_gratitude(message):
        return gratitude_reply(language=language)
    if is_explicitly_non_study(message):
        return polite_decline_reply(chapter_names=chapter_names, language=language)

    if not results:
        return (
            "Bonjour ! C'est avec grand plaisir que je vous aide. Pour mieux répondre à votre question, "
            "pourriez-vous la préciser en lien avec un chapitre ou une notion précise du cours ?"
        )
    r = results[0]
    raw_text = r.get("text", "")
    excerpt = raw_text[:320].rsplit(" ", 1)[0] + "…" if len(raw_text) > 320 else raw_text
    page = r.get("page", 1)
    chapter = r.get("chapter", "cours")

    if not settings.is_socratic:
        return (
            f"Voici ce que dit votre cours (page {page}, {chapter}) :\n\n{excerpt}\n\n"
            "(Le moteur d'IA n'est pas disponible pour le moment : vérifiez la clé API dans le fichier .env.)"
        )
    if hint_level == 1:
        return (
            f"Bonjour ! Travaillons cela ensemble avec plaisir. Avant d'aller plus loin : que savez-vous déjà sur cette notion ? "
            f"Prenez un instant pour relire la page {page} ({chapter}) et dites-moi avec vos propres mots quelle est l'idée clé."
        )
    if hint_level == 2:
        return (
            f"Très bonne démarche ! Voici un indice ciblé tiré de la page {page} : « {excerpt} ». "
            f"D'après vous, quelle notion fondamentale devez-vous utiliser ici ?"
        )
    if hint_level == 3:
        return (
            f"Vous avancez bien ! Essayons une analogie : imaginez ce concept appliqué à une situation concrète du quotidien. "
            f"En vous basant sur la page {page}, comment transposeriez-vous cette règle ?"
        )
    return (
        f"Voici l'explication complète et détaillée d'après votre cours (page {page}, {chapter}) :\n\n"
        f"{excerpt}\n\nPrenez le temps de relire ce passage : pouvez-vous me reformuler le principe essentiel pour valider que tout est clair ?"
    )


OFF_TOPIC_TAG = "[HORS_SUJET]"


def unit_context(db, course_id: int, unit_id, limit: int = 4) -> list[dict]:
    """Extraits du chapitre/unité courant (pour « résume cette unité », « reformule le point principal »...)."""
    from app.models import Chapter, Chunk

    if unit_id is None:
        return []
    try:
        uid = int(str(unit_id).strip())
    except ValueError:
        return []
    chapter = db.get(Chapter, uid)
    if not chapter or chapter.course_id != course_id:
        return []
    chunks = db.scalars(select(Chunk).where(Chunk.chapter_id == uid).order_by(Chunk.id).limit(limit)).all()
    return [{"text": c.text, "page": c.page, "chapter": chapter.title, "score": 0.0} for c in chunks]


def _merge_context(unit_chunks: list[dict], results: list[dict], cap: int = 6) -> list[dict]:
    seen, out = set(), []
    for r in unit_chunks + results:
        key = r["text"][:80]
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out[:cap]


def answer_reply(
    course_title: str,
    context: list[dict],
    message: str,
    history: list[dict],
    language: str,
    chapter_names: list[str] | None = None,
    hint_level: int = 1,
) -> tuple[str, bool, bool]:
    """Assistant spécialisé de la matière : répond à toute question liée au cours (RAG + connaissances).

    Retourne (réponse, hors_sujet, llm_utilisé)."""
    chapters_str = "; ".join((chapter_names or [])[:15]) or "non précisés"
    ctx = "\n\n".join(f"[Page {r['page']} — {r['chapter']}]\n{r['text'][:1200]}" for r in context) or "(aucun extrait trouvé)"
    system = (
        f"Tu es l'assistant pédagogique spécialisé du cours « {course_title} ». Tu te comportes comme un expert de cette "
        "matière, entraîné sur le support de cours ci-dessous, qui répond avec précision et clarté.\n\n"
        "PÉRIMÈTRE : tu réponds à TOUTE question liée à la matière du cours et à l'apprentissage "
        "(définitions, explications, exemples, exercices, résumés, reformulations, comparaisons, corrections, "
        "méthodes, préparation d'examen), qu'elle figure ou non mot pour mot dans les extraits.\n"
        f"Chapitres du cours : {chapters_str}.\n"
        "Seules les demandes SANS AUCUN rapport avec la matière ni avec les études (loisirs, sport, actualité people, "
        f"cuisine, etc.) sont déclinées : dans ce cas commence ta réponse EXACTEMENT par {OFF_TOPIC_TAG}, puis refuse en "
        "une ou deux phrases polies et propose 2-3 sujets du cours à travailler.\n\n"
        "COMMENT RÉPONDRE :\n"
        "1) Réponds DIRECTEMENT et complètement à la question. Ne renvoie JAMAIS l'étudiant à « relire une page » à la place "
        "de répondre, et ne réponds pas par une simple question.\n"
        "2) Appuie-toi d'abord sur les extraits du cours et cite les pages (ex. « p. 12 »).\n"
        "3) Si la réponse n'est pas dans les extraits mais relève de la matière, réponds avec tes connaissances en "
        "commençant par : « Ce point n'est pas détaillé dans votre cours, mais voici l'explication : ». "
        "N'invente jamais un contenu en l'attribuant au cours.\n"
        "4) Si la demande porte sur « cette unité / ce chapitre », utilise les extraits fournis.\n"
        "5) Format : clair et structuré (paragraphes courts, listes ou exemple si utile). Adapte la longueur à la question.\n"
        "6) Termine, si pertinent, par UNE courte question de vérification ou une suggestion pour continuer.\n"
        "7) Exception : si l'étudiant demande explicitement un indice ou à ne pas avoir la solution d'un exercice, "
        "guide-le pas à pas sans donner la solution brute.\n"
        f"8) Réponds dans la langue de l'étudiant (langue du cours : {language}).\n\n"
        f"EXTRAITS DU COURS :\n{ctx}"
    )
    msgs = [{"role": h.get("role", "user"), "content": h.get("content") or h.get("text", "")} for h in history[-10:]] + [
        {"role": "user", "content": message}
    ]
    out = llm.complete(system, msgs, max_tokens=1000, temperature=0.3)
    if not out:
        return _fallback_reply(context, message, 4, chapter_names, language), False, False
    if OFF_TOPIC_TAG in out[:40]:
        return out.replace(OFF_TOPIC_TAG, "", 1).strip(), True, True
    return out, False, True


def feynman_reply(results: list[dict], message: str, history: list[dict], language: str) -> dict:
    system = (
        "Tu joues le rôle d'un élève débutant curieux et très poli à qui l'étudiant explique un concept (méthode Feynman). "
        "Tu poses des questions naïves, demandes des exemples concrets et vérifies la clarté. "
        "Si l'étudiant parle de sujets non liés aux études, rappelle poliment que tu veux apprendre le cours.\n"
        f"Langue du cours : {language}.\n\nEXTRAITS DU COURS :\n{_context(results)}\n\n"
        'Réponds UNIQUEMENT en JSON : {"reply": "ta réponse d\'élève débutant polie (3 phrases max)", "score": entier 0-10, '
        '"gaps": ["points manquants ou erronés"]}'
    )
    msgs = [{"role": h.get("role", "user"), "content": h.get("content") or h.get("text", "")} for h in history[-6:]] + [
        {"role": "user", "content": message}
    ]
    data = llm.parse_json(llm.complete(system + "\nRéponds UNIQUEMENT en JSON valide.", msgs, max_tokens=600, temperature=0.4))
    if isinstance(data, dict) and data.get("reply"):
        return {"reply": str(data["reply"]), "score": data.get("score"), "gaps": data.get("gaps", [])}
    return {
        "reply": "Merci pour cette explication ! Comme je débute, pourriez-vous m'expliquer ce principe plus simplement, avec un exemple concret du cours ?",
        "score": None,
        "gaps": [],
    }
