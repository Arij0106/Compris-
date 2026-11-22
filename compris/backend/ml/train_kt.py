"""Entraînement du Knowledge Tracing (BKT) sur ASSISTments (ou tout dataset avec user / skill / correct / ordre).

Sortie : models/bkt_params.json  (+ métriques dans models/metrics.json)
Usage  : python -m ml.train_kt            (chemins/colonnes définis dans .env)
"""
import json
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, roc_auc_score

from app.services import bkt
from ml import config as cfg
from ml.bkt_fit import fit_bkt_grid
from ml.common import data_source, update_metrics


def load_interactions(path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset introuvable : {path}\n"
            "→ Placez votre fichier dans ./datasets/assistments/ et réglez ASSISTMENTS_PATH dans .env (voir README §4)."
        )
    header = pd.read_csv(path, nrows=0, encoding=cfg.KT_ENCODING, encoding_errors="replace").columns
    skill_col = cfg.KT_SKILL_COL if cfg.KT_SKILL_COL in header else "skill_name"
    needed = [cfg.KT_USER_COL, skill_col, cfg.KT_CORRECT_COL, cfg.KT_ORDER_COL]
    missing = [c for c in needed if c not in header]
    if missing:
        raise KeyError(f"Colonnes introuvables dans {path.name}: {missing}. Colonnes présentes: {list(header)[:25]}…")
    df = pd.read_csv(path, usecols=needed, encoding=cfg.KT_ENCODING, encoding_errors="replace", low_memory=False)
    df = df.rename(columns={cfg.KT_USER_COL: "user", skill_col: "skill", cfg.KT_CORRECT_COL: "correct", cfg.KT_ORDER_COL: "order"})
    df = df.dropna(subset=["user", "skill", "correct"])
    df["correct"] = pd.to_numeric(df["correct"], errors="coerce")
    df = df.dropna(subset=["correct"])
    df["correct"] = (df["correct"] >= 0.5).astype(int)
    df["order"] = pd.to_numeric(df["order"], errors="coerce").fillna(0)
    df["skill"] = df["skill"].astype(str).str.strip()
    df = df[~df["skill"].isin(["", "nan", "NA", "None"])]
    return df.sort_values("order", kind="stable")


def run(path=None) -> dict:
    path = path or cfg.ASSISTMENTS_PATH
    df = load_interactions(path)
    print(f"[KT] {len(df):,} interactions, {df['user'].nunique():,} étudiants, {df['skill'].nunique():,} compétences")

    counts = df.groupby("skill")["user"].nunique()
    skills = counts[counts >= cfg.KT_MIN_STUDENTS].sort_values(ascending=False).head(cfg.KT_MAX_SKILLS).index.tolist()
    if not skills:
        raise ValueError(f"Aucune compétence avec ≥ {cfg.KT_MIN_STUDENTS} étudiants (baissez KT_MIN_STUDENTS).")

    rng = np.random.RandomState(cfg.SEED)
    per_skill, all_y, all_bkt, all_base = {}, [], [], []
    n_inter = 0
    for skill in skills:
        sub = df[df["skill"] == skill]
        seqs_by_user = sub.groupby("user")["correct"].apply(list)
        seqs_by_user = seqs_by_user[seqs_by_user.map(len) >= 3]
        if len(seqs_by_user) < 20:
            continue
        users = seqs_by_user.index.to_numpy().copy()
        rng.shuffle(users)
        cut = int(0.8 * len(users))
        train = [seqs_by_user[u] for u in users[:cut]]
        test = [seqs_by_user[u] for u in users[cut:]]
        if len(train) > 3000:
            train = [train[i] for i in rng.choice(len(train), 3000, replace=False)]

        params = fit_bkt_grid(train)

        y, pb, pr = [], [], []
        for s in test:
            y += s
            pb += bkt.predict_sequence(s, params)
            c = 0
            for i, v in enumerate(s):  # baseline : taux de réussite courant de l'étudiant (lissé)
                pr.append((c + 1) / (i + 2))
                c += v
        y, pb, pr = np.array(y), np.array(pb), np.array(pr)
        auc = roc_auc_score(y, pb) if len(set(y)) > 1 else None
        per_skill[str(skill)] = {**params, "n_students": int(len(seqs_by_user)), "auc": None if auc is None else round(float(auc), 4)}
        all_y.append(y); all_bkt.append(pb); all_base.append(pr)
        n_inter += int(sum(len(s) for s in train) + len(y))
        print(f"[KT] compétence {skill}: {len(seqs_by_user)} étudiants, AUC={auc if auc is None else round(auc, 3)}")

    if not per_skill:
        raise ValueError("Pas assez de séquences exploitables.")

    w = np.array([v["n_students"] for v in per_skill.values()], dtype=float)
    global_params = {
        k: float(np.average([v[k] for v in per_skill.values()], weights=w)) for k in ("p_init", "p_learn", "p_guess", "p_slip")
    }
    y, pb, pr = np.concatenate(all_y), np.concatenate(all_bkt), np.concatenate(all_base)
    auc_bkt = round(float(roc_auc_score(y, pb)), 4) if len(set(y)) > 1 else 0.5
    auc_base = round(float(roc_auc_score(y, pr)), 4) if len(set(y)) > 1 else 0.5
    metrics = {
        "data_source": data_source(path),
        "dataset": path.name,
        "n_skills": len(per_skill),
        "n_test_interactions": int(len(y)),
        "auc_bkt": auc_bkt,
        "auc_baseline_running_accuracy": auc_base,
        "accuracy_bkt": round(float(accuracy_score(y, pb >= 0.5)), 4),
        "global_params": global_params,
    }
    cfg.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    (cfg.MODELS_DIR / "bkt_params.json").write_text(
        json.dumps({"global": global_params, "skills": per_skill}, indent=2)
    )
    update_metrics("knowledge_tracing", metrics)
    print(f"[KT] AUC BKT = {metrics['auc_bkt']} (baseline {metrics['auc_baseline_running_accuracy']}) → models/bkt_params.json")
    return metrics


if __name__ == "__main__":
    try:
        run()
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"ERREUR: {e}")
        sys.exit(1)
