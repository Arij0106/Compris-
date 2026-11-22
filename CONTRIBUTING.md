# Contribuer

1. Créez une branche : `git checkout -b feat/ma-fonctionnalite`
2. Backend : `pip install -r backend/requirements.txt`, puis testez avec `python backend/scripts/test_integration.py`
3. Frontend : `cd frontend && npm ci && npm run build`
4. Ouvrez une pull request en suivant le modèle fourni.

Règles : jamais de secrets ni de datasets dans les commits ; messages de commit courts à l’impératif (`feat:`, `fix:`, `docs:`).
