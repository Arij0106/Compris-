# Compris ? — Tuteur intelligent à partir de vos cours

Plateforme de tutorat : l’étudiant importe ses cours (PDF, Word, Excel, PowerPoint, texte), l’agent les découpe en **unités**, génère des **quiz**, détecte les **lacunes**, puis répond aux questions **à partir du cours** (RAG). Un suivi de maîtrise (**BKT**), une **révision espacée** (SM-2) et un **modèle de risque de décrochage** (OULAD) complètent le parcours.

```
┌──────────────┐   HTTP/JSON   ┌────────────────────────────────────────┐
│  Frontend    │ ────────────► │  Backend FastAPI                       │
│  Angular     │               │  RAG · LLM · BKT · SM-2 · risque       │
│  (3 panneaux)│ ◄──────────── │  SQLite / PostgreSQL                   │
└──────────────┘               └───────────────┬────────────────────────┘
                                               │ API compatible OpenAI
                                         Grok / Groq / OpenAI
```

## Contenu du dépôt

| Dossier | Rôle |
|---|---|
| [`backend/`](backend/) | API FastAPI, services (ingestion, RAG, tuteur, BKT, risque), scripts ML |
| [`frontend/`](frontend/) | Application Angular 22 (interface à trois panneaux) |
| [`docs/`](docs/) | Architecture, contrat d’API, ML, datasets, dossier de soumission |
| [`.github/`](.github/) | CI, modèles d’issues et de pull requests |

## Démarrage rapide

### Option A — Docker (tout-en-un)

```bash
cp backend/.env.example backend/.env     # puis renseignez UNE clé LLM (voir ci-dessous)
docker compose up --build
```

- Frontend : http://localhost:4200
- API : http://localhost:8000 — documentation interactive : http://localhost:8000/docs

### Option B — en local

```bash
# Backend (Python 3.11)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000

# Frontend (Node 22)
cd frontend
npm ci
npm start                                  # http://localhost:4200
```

## Configuration LLM

Dans `backend/.env`, renseignez **une** clé :

| Fournisseur | Variable | Remarque |
|---|---|---|
| Groq (offre gratuite) | `GROQ_API_KEY` | clé `gsk_…` |
| xAI Grok | `XAI_API_KEY` | clé `xai-…` |
| OpenAI ou compatible | `OPENAI_API_KEY` | Ollama, OpenRouter… |

Sans clé, l’application reste utilisable en **mode dégradé** (concepts TF-IDF, QCM à trous, indices génériques).

> ⚠️ Ne commitez jamais `backend/.env`. Il est dans `.gitignore`.

## Résultats ML (datasets réels)

| Modèle | Dataset | Métrique | Résultat |
|---|---|---|---|
| Knowledge tracing (BKT) | ASSISTments | AUC prochaine réponse | **0,718** (baseline 0,707) |
| Risque de décrochage | OULAD, jour 90 | AUC / précision / rappel | **0,828** / 0,766 / 0,595 |

Source : [`backend/models/metrics.json`](backend/models/metrics.json), exposé par `GET /ml/metrics`. Détails et limites : [docs/ML.md](docs/ML.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Contrat d’API](docs/API.md)
- [Modèles ML et honnêteté méthodologique](docs/ML.md)
- [Datasets : où les télécharger et les placer](docs/DATASETS.md)
- [Dossier de soumission (checklist, scénario de démo, limites)](docs/SUBMISSION.md)
- [Contribuer](CONTRIBUTING.md)

## Limites connues

- Pas d’authentification : `student_id` est une chaîne libre.
- PDF scannés (images) non supportés (pas d’OCR).
- Tables créées au démarrage, sans migrations.
- Seuils de classification « dans le cours / hors cours » à calibrer sur vos cours.

## Licence

[MIT](LICENSE)
