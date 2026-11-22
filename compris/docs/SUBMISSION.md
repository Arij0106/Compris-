# Dossier de soumission

## Résumé en une phrase

Un tuteur qui transforme les cours de l’étudiant en parcours de quiz, détecte ses lacunes et répond uniquement à partir de ses propres supports.

## Checklist avant de soumettre

- [ ] `backend/.env` **absent** du dépôt (`git ls-files | grep .env` ne doit lister que `.env.example`)
- [ ] Clé LLM utilisée pendant le développement **révoquée** et remplacée
- [ ] `docker compose up --build` fonctionne depuis un clone propre
- [ ] `GET /health` renvoie `status: ok` et `dropout_model: true`
- [ ] `GET /ml/metrics` renvoie des métriques `"data_source": "real"`
- [ ] README relu : commandes testées, liens valides
- [ ] Capture d’écran ou GIF de la démo ajouté dans `docs/` et référencé dans le README
- [ ] Licence présente ([LICENSE](../LICENSE))

## Scénario de démo (3 minutes)

1. Importer un cours PDF → cocher le cours → **Analyser**.
2. Faire le quiz de la première unité, volontairement avec 1 ou 2 erreurs.
3. Montrer les **lacunes** détectées et le retour par question.
4. Poser une question **dans le cours** puis une **hors sujet** : montrer la différence de réponse et les sources (page, chapitre).
5. Ouvrir `/ml/metrics` : AUC BKT 0,718 et AUC risque 0,828 sur données réelles.
6. Dashboard enseignant : maîtrise de classe, étudiants à risque.

## Points à dire honnêtement

- Les datasets calibrent BKT et le modèle de risque ; ils n’entraînent pas le LLM.
- Le risque dans l’app est un **proxy** des variables OULAD.
- BKT améliore peu la baseline (+0,011 AUC) : le gain principal est le suivi par concept.
- Pas d’authentification, pas d’OCR, pas de migrations.
