"""Ingestion d'un cours : extraction du texte, chapitres, chunks, concepts + prérequis."""
import logging
import math
import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Chapter, Chunk, Concept, Course
from app.services import llm
from app.services.text import STOPWORDS, clean, sentences

log = logging.getLogger(__name__)

SUPPORTED = {".pdf", ".pptx", ".txt", ".md"}


# --------------------------------------------------------------------------- extraction
def extract_pages(path: Path) -> list[tuple[int, str]]:
    """Retourne [(numéro_de_page, texte)]. Pour un PPTX, une page = une diapositive."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return [(i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages)]
    if ext == ".pptx":
        from pptx import Presentation

        pages = []
        for i, slide in enumerate(Presentation(str(path)).slides, 1):
            parts = [sh.text_frame.text for sh in slide.shapes if getattr(sh, "has_text_frame", False) and sh.has_text_frame]
            pages.append((i, "\n".join(parts)))
        return pages
    if ext in {".txt", ".md"}:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        step = 3000
        return [(i + 1, raw[k : k + step]) for i, k in enumerate(range(0, len(raw), step))]
    raise ValueError(f"Format non supporté: {ext}")


# --------------------------------------------------------------------------- nettoyage et chapitres
# Fix #5 : filtrage élargi des données administratives inutiles dans les PDF
ADMIN_BOILERPLATE_RE = re.compile(
    r"^\s*("
    # Noms d'institutions
    r"université|universite|faculté|faculte|institut|département|departement|école|ecole|académie|ministère|"
    r"republique\s+(algérienne|algerienne|tunisienne|française|francaise)|"
    # Termes académiques
    r"année universitaire|annee universitaire|semestre\s*[0-9]+|devoir surveillé|examen\s+(de|du|blanc)?|"
    r"session\s+(principale|rattrapage)?|licence|master|doctorat|filière|"
    r"domaine\s*:|spécialité\s*:|specialite\s*:|parcours\s*:|mention\s*:|"
    # Titres de personnes
    r"enseignant\s*:|professeur\s*:|docteur\s*:|dr\s*\.?\s*:|pr\s*\.?\s*:|"
    r"chargé\s+(de|du)\s+cours|chargé\s+de\s+td|responsable\s+du?\s+module|"
    # Pagination et dates
    r"page\s*[0-9]+(\s*/\s*[0-9]+)?|[0-9]+\s*/\s*[0-9]+|date\s*:|"
    r"[0-9]{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{2,4}|"
    r"[0-9]{1,2}\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+[0-9]{2,4}|"
    # Crédits, codes, emails
    r"crédits?\s*ects|code\s*module|filiere|"
    r"e-?mail\s*:|courriel\s*:|tél\.?\s*:|tel\s*:|fax\s*:|"
    # Copyright, sommaire, bibliographie
    r"©|copyright|tous\s+droits|all\s+rights|"
    r"sommaire|table\s+des\s+matières|table\s+of\s+contents|bibliographie|références|references|"
    r"remerciements|préface|preface"
    r")\b.*$",
    re.IGNORECASE,
)

CHAPTER_RE = re.compile(
    r"^\s*(chapitre|chapter|module|partie|part|unité|unite|unit|section|الفصل|الوحدة|الباب)\s+([0-9IVXivx]+)\s*[:.\-–—]?\s*(.*)$",
    re.IGNORECASE,
)


def _clean_page_lines(text: str) -> list[str]:
    """Élimine les en-têtes/pieds de page administratifs (dates, nom de fac, pagination)."""
    cleaned_lines = []
    for line in text.splitlines():
        line_s = line.strip()
        if not line_s:
            continue
        # Fix #5 : recherche du motif administratif partout dans la ligne, pas seulement au début
        if ADMIN_BOILERPLATE_RE.search(line_s):
            continue
        # Éliminer les lignes qui ne sont que des numéros de page ou pagination
        if re.match(r"^[-–—\s]*[0-9]+(\s*/\s*[0-9]+)?[-–—\s]*$", line_s):
            continue
        cleaned_lines.append(line_s)
    return cleaned_lines


def detect_chapters(pages: list[tuple[int, str]]) -> list[dict]:
    """Détecte les chapitres/unités pédagogiques réels et respecte la hiérarchie naturelle du cours."""
    pages = [(n, t) for n, t in pages if t.strip()]
    if not pages:
        return []
    starts, seen = [], set()
    for page_no, text in pages:
        cleaned_lines = _clean_page_lines(text)
        for line in cleaned_lines[:10]:
            m = CHAPTER_RE.match(line)
            if m:
                kind = m.group(1).capitalize()
                num = m.group(2)
                sub_title = m.group(3).strip()
                title = f"{kind} {num}"
                if sub_title and len(sub_title) > 2:
                    title += f" — {sub_title}"
                key = f"{kind.lower()} {num.lower()}"
                if key not in seen:
                    seen.add(key)
                    starts.append((page_no, title[:200]))
                break
    first, last = pages[0][0], pages[-1][0]
    chapters = []
    if len(starts) >= 2:
        starts.sort(key=lambda s: s[0])  # Garantie de l'ordre hiérarchique naturel
        starts[0] = (first, starts[0][1])
        for i, (p, title) in enumerate(starts):
            end = starts[i + 1][0] - 1 if i + 1 < len(starts) else last
            chapters.append({"title": title, "page_start": p, "page_end": max(p, end)})
    else:
        group = max(4, min(12, len(pages) // 4 or 6))
        for k, i in enumerate(range(0, len(pages), group), 1):
            sub = pages[i : i + group]
            chapters.append(
                {"title": f"Chapitre {k} (pages {sub[0][0]}–{sub[-1][0]})", "page_start": sub[0][0], "page_end": sub[-1][0]}
            )
    return chapters


# --------------------------------------------------------------------------- chunks
def chunk_pages(pages: list[tuple[int, str]], size: int, overlap: int) -> list[dict]:
    words: list[tuple[str, int]] = []
    for page_no, text in pages:
        # Fix #5 : nettoyer chaque page des en-têtes/pieds de page avant le découpage en chunks
        cleaned_lines = _clean_page_lines(text)
        cleaned_text = " ".join(cleaned_lines)
        words.extend((w, page_no) for w in clean(cleaned_text).split())
    chunks, step = [], max(1, size - overlap)
    for start in range(0, len(words), step):
        window = words[start : start + size]
        if len(window) < 20 and chunks:
            break
        chunks.append({"text": " ".join(w for w, _ in window), "page": window[0][1]})
        if start + size >= len(words):
            break
    return chunks


# --------------------------------------------------------------------------- concepts
FORBIDDEN_CONCEPT_WORDS = {
    "universite", "faculte", "institut", "departement", "annee", "semestre", "session",
    "examen", "devoir", "exercice", "exercices", "professeur", "enseignant", "docteur",
    "etudiant", "cours", "module", "chapitre", "partie", "section", "titre", "page", "pages",
    "premier", "premiere", "deuxieme", "troisieme", "quatrieme", "exemple", "exemples",
    "figure", "tableau", "table", "schema", "introduction", "conclusion", "resume",
    "date", "code", "credits", "ects", "filiere", "licence", "master", "doctorat",
    "auteur", "remerciements", "bibliographie", "sommaire", "copyright", "droits",
    "académie", "academie", "ecole", "école", "ecoles", "ministère", "ministere",
    "tp", "td", "diapo", "diapositive", "slide", "slides", "version",
}


def _is_valid_concept(name: str) -> bool:
    clean_n = name.lower().strip()
    clean_n = re.sub(r"[^\w\s-]", "", clean_n)
    if len(clean_n) < 3 or len(clean_n) > 50:
        return False
    if clean_n in FORBIDDEN_CONCEPT_WORDS:
        return False
    if re.match(r"^[0-9ivxlcdm\s_\-.:]+$", clean_n):
        return False
    # Fix #5 : rejet strict de tout concept contenant un mot administratif
    for forbidden in FORBIDDEN_CONCEPT_WORDS:
        if re.search(r"\b" + re.escape(forbidden) + r"\b", clean_n):
            return False
    return True


def _concepts_llm(title: str, text: str, language: str) -> list[dict] | None:
    system = (
        "Tu es un expert en ingénierie pédagogique. Tu extrais les concepts clés disciplinaires d'un chapitre de cours "
        f"(langue du cours : {language}).\n"
        "RÈGLE STRICTE : Ignore absolument tout élément administratif ou accessoire : noms d'universités, facultés, "
        "départements, dates, années scolaires, noms de professeurs, numéros de page, intitulés d'examens. "
        "N'extrais QUE des notions théoriques, scientifiques, techniques ou conceptuelles fondamentales enseignées dans ce chapitre."
    )
    user = (
        f"Chapitre : {title}\n\nTexte du chapitre :\n{text[:6000]}\n\n"
        'Donne 4 à 8 concepts réels sous forme JSON : [{"name": "...", "description": "définition pédagogique précise d\'une phrase", '
        '"prerequisites": ["autres concepts prérequis nécessaires"]}]'
    )
    data = llm.complete_json(system, user, max_tokens=1500)
    if not isinstance(data, list):
        return None
    out = []
    for d in data:
        if isinstance(d, dict):
            name = str(d.get("name", "")).strip()
            if _is_valid_concept(name):
                out.append(
                    {
                        "name": name[:120],
                        "description": str(d.get("description", "")).strip(),
                        "prerequisites": [str(p).strip() for p in d.get("prerequisites", []) if str(p).strip() and _is_valid_concept(str(p))],
                    }
                )
    return out or None


def _concepts_fallback(chapter_texts: list[str], per_chapter: int = 5) -> list[list[dict]]:
    """Sans LLM : mots-clés TF-IDF disciplinaires par chapitre (filtrage strict du bruit administratif)."""
    n = len(chapter_texts)
    vec = TfidfVectorizer(
        stop_words=sorted(STOPWORDS),
        ngram_range=(1, 2),
        token_pattern=r"(?u)\b[a-zA-ZÀ-ÿ\u0600-\u06FF]{4,}\b",
        max_df=0.8 if n >= 3 else 1.0,
        sublinear_tf=True,
    )
    try:
        X = vec.fit_transform(chapter_texts)
    except ValueError:
        return [[] for _ in chapter_texts]
    terms = vec.get_feature_names_out()
    result = []
    for i, text in enumerate(chapter_texts):
        row = X[i].toarray().ravel()
        chosen: list[str] = []
        for j in row.argsort()[::-1]:
            if row[j] <= 0 or len(chosen) >= per_chapter:
                break
            t = terms[j]
            if not _is_valid_concept(t):
                continue
            if any(t in c or c in t for c in chosen):
                continue
            chosen.append(t)
        sents = sentences(text)
        concepts = []
        for t in chosen:
            # Recherche une phrase explicative contenant le concept entier
            word_pattern = re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE)
            desc = next((s for s in sents if word_pattern.search(s) and len(s) > 30), "")
            if not desc:
                desc = f"Concept clé abordé dans ce chapitre concernant {t}."
            concepts.append({"name": t.capitalize(), "description": desc[:250], "prerequisites": []})
        result.append(concepts)
    return result


def _link_prerequisites_fallback(concepts: list[dict]) -> None:
    """Sans LLM : un concept d'un chapitre antérieur cité dans la description devient prérequis."""
    for c in concepts:
        desc = c["description"].lower()
        c["prerequisites"] = [
            o["name"] for o in concepts if o["chapter_idx"] < c["chapter_idx"] and o["name"].lower() in desc
        ]


# --------------------------------------------------------------------------- orchestration
def ingest_course(db: Session, course: Course, pages: list[tuple[int, str]]) -> None:
    pages = [(n, t) for n, t in pages if t.strip()]
    chapters = detect_chapters(pages)
    if not chapters:
        raise ValueError("Aucun texte exploitable dans le document (PDF scanné ? essayez un PDF avec texte).")

    chapter_rows, chapter_texts = [], []
    for idx, ch in enumerate(chapters, 1):
        # Fix #5 : filtrer les lignes administratives pour chaque sous-ensemble de pages
        sub = [(n, "\n".join(_clean_page_lines(t))) for n, t in pages if ch["page_start"] <= n <= ch["page_end"]]
        sub = [(n, t) for n, t in sub if t.strip()]
        row = Chapter(course_id=course.id, idx=idx, title=ch["title"], page_start=ch["page_start"], page_end=ch["page_end"])
        db.add(row)
        db.flush()
        chapter_rows.append(row)
        chapter_texts.append(clean(" ".join(t for _, t in sub)))
        for c in chunk_pages(sub, settings.chunk_size_words, settings.chunk_overlap_words):
            db.add(Chunk(course_id=course.id, chapter_id=row.id, page=c["page"], text=c["text"]))

    # concepts
    per_chapter: list[list[dict]] = []
    used_llm = False
    if llm.is_enabled():
        for row, text in zip(chapter_rows, chapter_texts):
            res = _concepts_llm(row.title, text, course.language)
            per_chapter.append(res or [])
            used_llm = used_llm or bool(res)
    if not used_llm:
        per_chapter = _concepts_fallback(chapter_texts)

    flat: list[dict] = []
    seen: set[str] = set()
    cap = settings.max_concepts
    # répartition équitable : on prend en round-robin pour couvrir tous les chapitres
    for rank in range(max((len(p) for p in per_chapter), default=0)):
        for ci, lst in enumerate(per_chapter):
            if rank < len(lst) and len(flat) < cap and lst[rank]["name"].lower() not in seen:
                item = dict(lst[rank], chapter_idx=ci)
                seen.add(item["name"].lower())
                flat.append(item)
    flat.sort(key=lambda c: c["chapter_idx"])

    # Filet de sécurité si aucun concept n'a pu être extrait automatiquement
    if not flat and chapter_rows:
        flat = [{"name": ch.title, "description": ch.title, "prerequisites": [], "chapter_idx": i} for i, ch in enumerate(chapter_rows)]

    if not used_llm:
        _link_prerequisites_fallback(flat)

    name_to_row: dict[str, Concept] = {}
    for c in flat:
        row = Concept(
            course_id=course.id,
            chapter_id=chapter_rows[c["chapter_idx"]].id,
            name=c["name"],
            description=c["description"],
            prerequisites=[],
        )
        db.add(row)
        db.flush()
        name_to_row[c["name"].lower()] = row
    for c in flat:
        me = name_to_row[c["name"].lower()]
        me.prerequisites = [
            name_to_row[p.lower()].id for p in c["prerequisites"] if p.lower() in name_to_row and name_to_row[p.lower()].id != me.id
        ]
    db.flush()
