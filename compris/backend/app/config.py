"""Configuration centrale, lue depuis les variables d'environnement / le fichier .env."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Base de données
    database_url: str = f"sqlite:///{BASE_DIR / 'storage' / 'app.db'}"
    storage_dir: Path = BASE_DIR / "storage"
    models_dir: Path = BASE_DIR / "models"

    # CORS (adresse du frontend)
    cors_origins: str = "*"

    # LLM (tous les fournisseurs ci-dessous utilisent le format OpenAI /chat/completions)
    llm_provider: str = "auto"  # "auto" | "grok" | "groq" | "openai" | "none"
    llm_timeout: float = 60.0

    # Grok (xAI)  -> https://console.x.ai
    xai_api_key: str = ""
    xai_base_url: str = "https://api.x.ai/v1"
    xai_model: str = "grok-3-mini"

    # Groq (offre gratuite, modèles Llama)  -> https://console.groq.com
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"

    # OpenAI ou tout serveur compatible (Ollama, OpenRouter...)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # Style du tuteur : "direct" = répond complètement à toute question de la matière (recommandé)
    #                   "socratic" = ne donne que des indices progressifs (ancien comportement)
    tutor_style: str = "direct"  # "direct" | "socratic"

    @property
    def is_socratic(self) -> bool:
        return self.tutor_style.lower().strip().startswith("socrat")

    # Ingestion / RAG
    chunk_size_words: int = 180
    chunk_overlap_words: int = 30
    max_concepts: int = 25
    questions_per_concept: int = 3
    in_course_threshold: float = 0.12   # score cosinus TF-IDF >= seuil -> question "dans le cours"
    related_threshold: float = 0.04     # entre les deux seuils -> "hors cours" ; en dessous -> "hors sujet"

    # Risque
    risk_high: float = 0.66
    risk_medium: float = 0.33


settings = Settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)
(settings.storage_dir / "uploads").mkdir(parents=True, exist_ok=True)
settings.models_dir.mkdir(parents=True, exist_ok=True)
