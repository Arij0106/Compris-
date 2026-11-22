# Modèles ML

Les datasets servent à **calibrer et valider** deux modèles. Ils n’entraînent pas le LLM.

## Knowledge tracing (BKT) — ASSISTments

- Paramètres `p_init`, `p_learn`, `p_guess`, `p_slip` ajustés par maximum de vraisemblance, par compétence.
- Les paramètres moyens servent à suivre la maîtrise de chaque concept des cours importés.
- Métrique : AUC de prédiction de la prochaine réponse, comparée à une baseline (taux de réussite courant).
- Résultat (`models/metrics.json`) : AUC BKT **0,7179** vs baseline **0,7074** ; 30 compétences ; 31 560 interactions de test.

## Risque de décrochage — OULAD

- Régression logistique et gradient boosting sur 3 variables : `avg_score`, `completion_rate`, `active_days_ratio`, calculées jusqu’au jour 90 (pas de fuite de données).
- Meilleur modèle : gradient boosting, AUC **0,8277**, précision 0,7656, rappel 0,5949, F1 0,6694.
- Dans l’application, les variables sont approximées par le taux de bonnes réponses, la part des concepts travaillés et la régularité d’activité. C’est un **proxy**, pas une équivalence exacte : à dire explicitement lors de la présentation.

## Réentraîner

```bash
cd backend
python scripts/verify_setup.py        # vérifie les datasets
python -m ml.train_all                # datasets réels
python -m ml.train_all --synthetic    # faux datasets (test du pipeline uniquement)
```

Les métriques synthétiques sont marquées `"data_source": "synthetic"` et ne doivent jamais être présentées comme réelles.
