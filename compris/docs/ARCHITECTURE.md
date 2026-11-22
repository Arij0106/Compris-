# Architecture

## Vue d’ensemble

- **Frontend** (`frontend/`) : Angular 22, composants autonomes, état central dans `WorkspaceStore` (signals). Quatre zones : `sources-panel` (import), `stage-panel` (étude/quiz/résultat), `chat-panel` (questions), `journey-panel` (unités, lacunes). Les appels HTTP passent par `core/api.service.ts`. `core/config.ts` contient `apiUrl` et `useMock`.
- **Backend** (`backend/app/`) : FastAPI.
  - `routers/` : `courses` (upload, analyze), `learning` (quiz, evaluate, answer, profile, review), `chat`, `teacher`.
  - `services/` : `ingestion` (PDF/PPTX/TXT → chapitres → chunks → concepts), `retrieval` (TF-IDF), `questions` (banque de QCM), `tutor` (modes direct, socratique, Feynman), `bkt` / `knowledge_tracing`, `spaced` (SM-2), `risk`, `selection`, `llm` (client compatible OpenAI).
- **ML** (`backend/ml/`) : entraînement hors API ; artefacts écrits dans `backend/models/`.
- **Données** : SQLite par défaut (`backend/storage/app.db`), PostgreSQL via `DATABASE_URL`.

## Flux principal

1. `POST /upload` → fichier stocké, texte extrait, chapitres/chunks/concepts créés ; la banque de questions se génère en arrière-plan.
2. `POST /analyze` → unités d’étude pour les cours sélectionnés.
3. `GET /quiz` → questions d’une unité.
4. `POST /evaluate` → score, lacunes, retour par question ; la maîtrise (BKT) est mise à jour.
5. `POST /chat` → réponse issue du RAG, classée `in_course` / `out_of_course` / `off_topic`.
6. `GET /review` + `POST /review/grade` → cartes dues (SM-2).
7. `GET /teacher/dashboard` → maîtrise de classe et étudiants à risque.

## Choix de conception

- **RAG TF-IDF** : léger, sans dépendance GPU. Remplaçable par des embeddings en ne modifiant que `services/retrieval.py`.
- **Fournisseur LLM interchangeable** : tout passe par le format `/chat/completions`.
- **Mode dégradé** sans clé : la démo ne plante jamais faute de LLM.
