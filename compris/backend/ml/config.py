"""Chemins et noms de colonnes des datasets — tout se règle via .env (voir .env.example).
Supporte l'exécution locale (Windows/Linux/Mac) et dans conteneur Docker (/app/...).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _resolve_path(env_val: str | None, default: Path) -> Path:
    """Résout un chemin absolu, relatif, ou de type conteneur (/app/...)."""
    if not env_val:
        return default
    p = Path(env_val)
    if p.exists():
        return p
    # Si le chemin commence par /app/ et qu'on tourne hors conteneur
    str_val = str(env_val).replace("\\", "/")
    if str_val.startswith("/app/"):
        rel = str_val.removeprefix("/app/")
        host_p = ROOT / rel
        if host_p.exists():
            return host_p
        return host_p
    return p


DATASETS_DIR = _resolve_path(os.getenv("DATASETS_DIR"), ROOT / "datasets")
MODELS_DIR = _resolve_path(os.getenv("MODELS_DIR"), ROOT / "models")


def _find_assistments_path() -> Path:
    """Trouve le fichier ASSISTments dans datasets/assistments (skill_builder_data.csv ou variante)."""
    env_p = os.getenv("ASSISTMENTS_PATH")
    p = _resolve_path(env_p, DATASETS_DIR / "assistments" / "skill_builder_data_corrected_collapsed.csv")
    if p.exists():
        return p
    # Alternatives courantes
    candidates = [
        DATASETS_DIR / "assistments" / "skill_builder_data_corrected_collapsed.csv",
        DATASETS_DIR / "assistments" / "skill_builder_data.csv",
    ]
    for c in candidates:
        if c.exists():
            return c
    # Tout premier CSV présent dans datasets/assistments
    assist_dir = DATASETS_DIR / "assistments"
    if assist_dir.exists():
        csvs = list(assist_dir.glob("*.csv"))
        if csvs:
            return csvs[0]
    return p


# ---- Knowledge tracing (ASSISTments par défaut ; adaptable à EdNet, Junyi...) ----
ASSISTMENTS_PATH = _find_assistments_path()
KT_ENCODING = os.getenv("KT_ENCODING", "latin-1")
KT_USER_COL = os.getenv("KT_USER_COL", "user_id")
KT_SKILL_COL = os.getenv("KT_SKILL_COL", "skill_id")
KT_CORRECT_COL = os.getenv("KT_CORRECT_COL", "correct")
KT_ORDER_COL = os.getenv("KT_ORDER_COL", "order_id")
KT_MAX_SKILLS = int(os.getenv("KT_MAX_SKILLS", "30"))
KT_MIN_STUDENTS = int(os.getenv("KT_MIN_STUDENTS", "50"))

# ---- Décrochage (OULAD) ----
OULAD_DIR = _resolve_path(os.getenv("OULAD_DIR"), DATASETS_DIR / "oulad")
OULAD_CUTOFF_DAY = int(os.getenv("OULAD_CUTOFF_DAY", "90"))

SEED = 42
