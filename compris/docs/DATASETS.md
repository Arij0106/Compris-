# Datasets

Les datasets ne sont **pas versionnés** (OULAD `studentVle.csv` pèse environ 450 Mo). Placez-les dans `backend/datasets/`.

| Dataset | Source | Emplacement |
|---|---|---|
| ASSISTments Skill Builder | https://sites.google.com/site/assistmentsdata/ | `backend/datasets/assistments/skill_builder_data_corrected_collapsed.csv` |
| OULAD | https://analyse.kmi.open.ac.uk/open_dataset | `backend/datasets/oulad/` : `studentInfo`, `assessments`, `studentAssessment`, `studentVle`, `studentRegistration`, `courses`, `vle` (`.csv`) |

Les chemins du `.env` sont vus depuis le conteneur (`/app/datasets/...`). Autre dataset de knowledge tracing : réglez `ASSISTMENTS_PATH` et `KT_USER_COL`, `KT_SKILL_COL`, `KT_CORRECT_COL`, `KT_ORDER_COL`.

Respectez les licences et conditions d’usage de chaque dataset.
