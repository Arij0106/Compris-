# Backend — Plateforme de tutorat socratique

API **FastAPI** + base **SQLite/PostgreSQL** + RAG sur les cours + tuteur socratique (LLM) + suivi de maîtrise (BKT) + révision espacée (SM-2) + modèle de risque (OULAD) + dashboard enseignant. Le tout dans un conteneur **Docker**.

## 1. Structure

```
backend/
├── Dockerfile · docker-compose.yml · requirements.txt · .env.example
├── app/                         ← l'API
│   ├── main.py                  point d'entrée (CORS, routes)
│   ├── config.py · database.py · models.py · schemas.py
│   ├── routers/  courses.py (upload) · learning.py (quiz, answer, profile, review)
│   │             chat.py (tuteur) · teacher.py (dashboard, ml/metrics, health)
│   └── services/ ingestion.py (PDF→chapitres→chunks→concepts) · retrieval.py (RAG)
│                 questions.py (banque de QCM) · tutor.py (socratique + Feynman)
│                 bkt.py · knowledge_tracing.py · spaced.py (SM-2) · risk.py · selection.py · llm.py
├── ml/                          ← entraînement (hors API)
│   ├── train_kt.py (ASSISTments → BKT) · train_oulad.py (OULAD → risque)
│   ├── train_all.py · make_synthetic.py (faux datasets pour tester)
├── datasets/   ← VOS datasets (monté dans le conteneur)
├── models/     ← modèles entraînés + metrics.json (généré)
└── storage/    ← base SQLite + cours uploadés (généré)
```

## 2. Démarrage rapide

```bash
cp .env.example .env          # puis éditez .env (clé API, chemins datasets)
docker compose up --build     # API sur http://localhost:8000  ·  doc interactive : /docs
```

Le tuteur répond par défaut en mode **direct** (`TUTOR_STYLE=direct`) : il répond complètement à toute question liée à la matière du cours, en s'appuyant sur le RAG, et décline poliment le reste. `TUTOR_STYLE=socratic` rétablit le mode indices progressifs.

Sans clé API (`LLM_PROVIDER=none` ou clé vide), tout fonctionne en **mode dégradé** : concepts par mots-clés TF-IDF, QCM « texte à trous », indices génériques. Pour la démo, **mettez une clé** : la qualité est sans comparaison.

## 3. ✅ Ce que VOUS devez renseigner

| Quoi | Où | Détail |
|---|---|---|
| Clé API LLM | `.env` → `XAI_API_KEY` (Grok) ou `GROQ_API_KEY` (Groq, gratuit) | modèle réglable via `XAI_MODEL` / `GROQ_MODEL` |
| Adresse de votre frontend | `.env` → `CORS_ORIGINS` | ex. `http://localhost:5173` (ou `*` en dev) |
| Dataset knowledge tracing | `datasets/` + `.env` → `ASSISTMENTS_PATH` | voir §4 |
| Dataset décrochage | `datasets/oulad/` + `.env` → `OULAD_DIR` | voir §4 |
| Frontend | chez vous | appelle les routes du §5 |

## 4. Datasets : où les mettre

Les chemins du `.env` sont **vus depuis le conteneur** : votre dossier `./datasets/` apparaît comme `/app/datasets/`.

**ASSISTments** (knowledge tracing) — fichier `skill_builder_data_corrected_collapsed.csv` (ou `skill_builder_data.csv`) :
```
./datasets/assistments/skill_builder_data_corrected_collapsed.csv     →  ASSISTMENTS_PATH=/app/datasets/assistments/skill_builder_data_corrected_collapsed.csv
```
Colonnes lues : `user_id`, `skill_id` (sinon `skill_name`), `correct`, `order_id`. Encodage `latin-1` par défaut (`KT_ENCODING`). Le code détecte automatiquement la variante du fichier présente dans `datasets/assistments/`.

**Autre dataset de KT (EdNet, Junyi, Statics2011…)** : même principe, il suffit que votre CSV ait une colonne étudiant, compétence, réussite (0/1) et un ordre chronologique ; réglez `ASSISTMENTS_PATH` et `KT_USER_COL`, `KT_SKILL_COL`, `KT_CORRECT_COL`, `KT_ORDER_COL`. Aucun code à modifier.

**OULAD** — dossier avec ces CSV (téléchargeables sur analyse.kmi.open.ac.uk/open_dataset) :
```
./datasets/oulad/studentInfo.csv  assessments.csv  studentAssessment.csv  studentVle.csv
./datasets/oulad/studentRegistration.csv  courses.csv  vle.csv  (recommandés)  →  OULAD_DIR=/app/datasets/oulad
```

**Vérifier vos datasets :**
```bash
python scripts/verify_setup.py
```

**Entraîner :**
```bash
docker compose run --rm backend python -m ml.train_all        # vos vrais datasets
docker compose restart backend                                # recharge les modèles
```
Résultat : `models/bkt_params.json`, `models/dropout_model.joblib`, `models/metrics.json` (AUC, précision, rappel…) — exposé par `GET /ml/metrics`, **à afficher dans votre démo**.

Pour tester le pipeline avant d'avoir vos fichiers : `python -m ml.train_all --synthetic` (faux datasets, métriques marquées `"data_source": "synthetic"` : **ne jamais les présenter comme réelles**).

### Ce que font réellement les modèles (à dire honnêtement au jury)
- **BKT** : paramètres (p_init, p_learn, p_guess, p_slip) ajustés par maximum de vraisemblance sur ASSISTments, par compétence ; les **paramètres moyens** servent ensuite à suivre chaque concept de *vos* cours. Métrique : AUC de prédiction de la prochaine réponse, comparée à une baseline (taux de réussite courant).
- **Risque (OULAD)** : régression logistique / gradient boosting sur 3 variables sans échelle, calculées jusqu'au jour 90 (prédiction précoce, pas de fuite). Dans l'app, elles sont approximées par : taux de bonnes réponses, part des concepts travaillés, régularité d'activité. C'est un **proxy**, pas une équivalence exacte : le dire dans le pitch.
- Les datasets servent à **calibrer/valider** ces deux modèles, pas à entraîner un LLM.

## 5. API (contrat)

| Route | Corps / paramètres | Réponse |
|---|---|---|
| `POST /upload` | multipart : `file` (pdf/pptx/txt/md), `title?`, `language?` (fr, ar, en) | `{course_id, chapters:[{id,title}], concepts:[{id,name}], questions_status}` |
| `GET /courses/{id}` | | idem + `status`, `questions_status` (`pending/running/ready/error`), `n_questions` |
| `GET /quiz` | `course_id`, `concept_id?`, `student_id?`, `n?` | `{questions:[{id,text,choices[4],concept,bloom_level,difficulty}], questions_status}` |
| `POST /answer` | `{student_id, question_id, choice_index (0-3), time_spent?}` | `{correct, correct_index, explanation, next_question_id, mastery:{concept_id: 0..1}}` |
| `GET /profile` | `student_id`, `course_id?` | `{concepts:[{id,name,mastery,attempts,risk,recommendation}], global_risk, global_risk_score}` |
| `POST /chat` | `{student_id, course_id, message, history?, hint_level? (1-4), mode? ("socratic"\|"feynman")}` | `{reply, sources:[{page,chapter}], type:"in_course\|out_of_course\|off_topic", next_hint_level?}` (+ `score`, `gaps` en mode Feynman) |
| `GET /review` | `student_id`, `course_id?` | `{cards:[{id,front,back,due_date,concept}]}` (cartes dues) |
| `POST /review/grade` | `{student_id, card_id, quality 0-5}` | prochaine échéance (SM-2) |
| `GET /teacher/dashboard` | `course_id` | `{class_mastery:[{concept,avg}], at_risk_count, hardest_concepts[], n_students}` |
| `GET /ml/metrics` · `GET /health` | | métriques ML · état (LLM actif, modèle chargé) |

Notes pour votre frontend :
- `student_id` est une **chaîne libre** (créée automatiquement à la première utilisation) : pas d'authentification dans cette version. Générez-en un et gardez-le dans le `localStorage`.
- Après `/upload`, la banque de questions se génère **en arrière-plan** : interrogez `GET /courses/{id}` jusqu'à `questions_status == "ready"` avant d'afficher le quiz.
- Mode socratique : le frontend incrémente `hint_level` (1→4) tant que l'étudiant reste bloqué ; la réponse renvoie `next_hint_level`.
- Documentation interactive de toutes les routes : `http://localhost:8000/docs`.

## 6. Calibrage important : le chat « dans le cours / hors cours »

La classification utilise la similarité TF-IDF entre la question et les passages du cours. Les seuils `IN_COURSE_THRESHOLD` (0.12) et `RELATED_THRESHOLD` (0.04) sont des **valeurs de départ** : testez 10 questions dans le cours et 10 hors cours sur votre vrai PDF, regardez les scores, ajustez dans `.env`. Pour de meilleurs résultats : remplacer TF-IDF par des embeddings (changer seulement `app/services/retrieval.py`).

## 7. PostgreSQL (optionnel)
Dans `.env` : `DATABASE_URL=postgresql+psycopg2://tutor:tutor@postgres:5432/tutor`, puis `docker compose --profile postgres up --build`.

## 8. Limites connues
- PDF scannés (images) non supportés : il faut un PDF avec du texte (OCR à ajouter sinon).
- Pas d'authentification ni de rôle enseignant/étudiant.
- Les tables sont créées automatiquement au démarrage (pas de migrations) : si vous modifiez `models.py`, supprimez `storage/app.db`.
