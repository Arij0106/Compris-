"""Entraînement du modèle de risque de décrochage/échec sur OULAD (Open University Learning Analytics Dataset).

Fichiers CSV requis dans OULAD_DIR : studentInfo, assessments, studentAssessment, studentVle
Recommandé : studentRegistration (pour exclure les étudiants déjà partis avant la date de coupure).

Cible    : final_result ∈ {Withdrawn, Fail} → 1 (à risque), {Pass, Distinction} → 0
Variables (3, sans échelle, calculées jusqu'au jour OULAD_CUTOFF_DAY — prédiction PRÉCOCE, pas de fuite d'information) :
  avg_score, completion_rate, active_days_ratio   (voir app/services/risk.py pour l'équivalent dans l'app)
Sortie   : models/dropout_model.joblib (+ métriques dans models/metrics.json)
Usage    : python -m ml.train_oulad
"""
import sys

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ml import config as cfg
from ml.common import data_source, update_metrics

FEATURES = ["avg_score", "completion_rate", "active_days_ratio"]
KEY = ["code_module", "code_presentation", "id_student"]


def _read(d, name, **kw):
    p = d / name
    if not p.exists():
        raise FileNotFoundError(f"Fichier OULAD manquant : {p}\n→ Voir README §4 (dossier OULAD_DIR).")
    kw.setdefault("na_values", ["?"])
    return pd.read_csv(p, **kw)


def build_features(d, cutoff: int) -> pd.DataFrame:
    info = _read(d, "studentInfo.csv", usecols=KEY + ["final_result"])
    assess = _read(d, "assessments.csv")
    assess["date"] = pd.to_numeric(assess["date"], errors="coerce")
    due = assess[(assess["assessment_type"] != "Exam") & (assess["date"] <= cutoff)]
    n_due = due.groupby(["code_module", "code_presentation"]).size().rename("n_due").reset_index()

    sa = _read(d, "studentAssessment.csv", usecols=["id_assessment", "id_student", "date_submitted", "score"])
    sa["date_submitted"] = pd.to_numeric(sa["date_submitted"], errors="coerce")
    sa["score"] = pd.to_numeric(sa["score"], errors="coerce")
    sa = sa.merge(due[["id_assessment", "code_module", "code_presentation"]], on="id_assessment")
    sa = sa[sa["date_submitted"] <= cutoff]
    sa_agg = (
        sa.groupby(KEY).agg(n_sub=("id_assessment", "nunique"), avg_score=("score", "mean")).reset_index()
    )

    if not (d / "studentVle.csv").exists():
        _raise_missing(d / "studentVle.csv")
    parts = []  # studentVle est volumineux (~10 M lignes) : lecture par morceaux
    for chunk in pd.read_csv(d / "studentVle.csv", usecols=KEY + ["date"], na_values=["?"], chunksize=1_000_000):
        chunk["date"] = pd.to_numeric(chunk["date"], errors="coerce")
        chunk = chunk[(chunk["date"] >= 0) & (chunk["date"] <= cutoff)]
        parts.append(chunk.drop_duplicates())
    vle = pd.concat(parts).drop_duplicates()
    vle_agg = vle.groupby(KEY).size().rename("active_days").reset_index()

    df = info.merge(n_due, on=["code_module", "code_presentation"])  # garde les présentations ayant des évaluations avant la coupure
    df = df.merge(sa_agg, on=KEY, how="left").merge(vle_agg, on=KEY, how="left")

    reg_path = d / "studentRegistration.csv"
    if reg_path.exists():  # exclut ceux qui se sont désinscrits avant la coupure (sinon la tâche est triviale)
        reg = pd.read_csv(reg_path, usecols=KEY + ["date_unregistration"], na_values=["?"])
        reg["date_unregistration"] = pd.to_numeric(reg["date_unregistration"], errors="coerce")
        df = df.merge(reg, on=KEY, how="left")
        df = df[~(df["date_unregistration"] <= cutoff)]
    else:
        print("[OULAD] studentRegistration.csv absent : étudiants déjà partis non exclus (résultats plus optimistes).")

    df[["n_sub", "avg_score", "active_days"]] = df[["n_sub", "avg_score", "active_days"]].fillna(0)
    df["completion_rate"] = (df["n_sub"] / df["n_due"]).clip(0, 1).fillna(0)
    df["active_days_ratio"] = (df["active_days"] / (cutoff + 1)).clip(0, 1).fillna(0)
    df["at_risk"] = df["final_result"].isin(["Withdrawn", "Fail"]).astype(int)
    return df


def _raise_missing(p):
    raise FileNotFoundError(f"Fichier OULAD manquant : {p}\n→ Voir README §4 (dossier OULAD_DIR).")


def run(directory=None) -> dict:
    d = directory or cfg.OULAD_DIR
    df = build_features(d, cfg.OULAD_CUTOFF_DAY)
    print(f"[OULAD] {len(df):,} inscriptions étudiant-cours, {df['at_risk'].mean():.1%} à risque")

    X, y, groups = df[FEATURES], df["at_risk"], df["id_student"]
    X = X.fillna(0)
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=cfg.SEED).split(X, y, groups))
    models = {
        "logreg": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced")),
        "gradient_boosting": HistGradientBoostingClassifier(max_depth=3, max_iter=150, random_state=cfg.SEED),
    }
    res = {}
    for name, m in models.items():
        m.fit(X.iloc[tr], y.iloc[tr])
        res[name] = roc_auc_score(y.iloc[te], m.predict_proba(X.iloc[te])[:, 1])
        print(f"[OULAD] {name}: AUC = {res[name]:.3f}")
    best = max(res, key=res.get)
    model = models[best]
    pred = model.predict_proba(X.iloc[te])[:, 1]
    label = (pred >= 0.5).astype(int)

    cfg.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": FEATURES, "cutoff_day": cfg.OULAD_CUTOFF_DAY}, cfg.MODELS_DIR / "dropout_model.joblib")
    metrics = {
        "data_source": data_source(d),
        "dataset": "OULAD",
        "cutoff_day": cfg.OULAD_CUTOFF_DAY,
        "features": FEATURES,
        "n_train": int(len(tr)),
        "n_test": int(len(te)),
        "positive_rate": round(float(y.mean()), 4),
        "best_model": best,
        "auc_logreg": round(float(res["logreg"]), 4),
        "auc_gradient_boosting": round(float(res["gradient_boosting"]), 4),
        "auc": round(float(res[best]), 4),
        "accuracy": round(float(accuracy_score(y.iloc[te], label)), 4),
        "precision": round(float(precision_score(y.iloc[te], label, zero_division=0)), 4),
        "recall": round(float(recall_score(y.iloc[te], label, zero_division=0)), 4),
        "f1": round(float(f1_score(y.iloc[te], label, zero_division=0)), 4),
    }
    update_metrics("dropout", metrics)
    print(f"[OULAD] meilleur modèle : {best} (AUC {metrics['auc']}) → models/dropout_model.joblib")
    return metrics


if __name__ == "__main__":
    try:
        run()
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"ERREUR: {e}")
        sys.exit(1)
