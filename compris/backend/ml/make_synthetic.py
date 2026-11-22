"""Génère de FAUX datasets (formats ASSISTments / OULAD) pour tester le pipeline sans attendre vos vrais fichiers.

⚠ Les métriques obtenues sont marquées "data_source": "synthetic" — ne jamais les présenter comme des résultats réels.
Usage : python -m ml.make_synthetic
"""
import numpy as np
import pandas as pd

from ml import config as cfg

SYN = cfg.DATASETS_DIR / "_synthetic"


def make_assistments(n_students=600, n_skills=6, seed=0) -> "Path":
    rng = np.random.RandomState(seed)
    rows, order = [], 0
    for skill in range(1, n_skills + 1):
        g, s, t, p0 = rng.uniform(0.1, 0.3), rng.uniform(0.05, 0.15), rng.uniform(0.1, 0.3), rng.uniform(0.2, 0.5)
        for u in range(1, n_students + 1):
            known = rng.rand() < p0
            for _ in range(rng.randint(4, 25)):
                correct = int(rng.rand() < ((1 - s) if known else g))
                order += 1
                rows.append((order, u, skill, correct))
                known = known or rng.rand() < t
    path = SYN / "assistments" / "skill_builder_data.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=["order_id", "user_id", "skill_id", "correct"]).sample(frac=1, random_state=seed)
    df.sort_values("order_id").to_csv(path, index=False)
    return path


def make_oulad(n=3000, seed=1) -> "Path":
    rng = np.random.RandomState(seed)
    d = SYN / "oulad"
    d.mkdir(parents=True, exist_ok=True)
    mod, pres = "AAA", "2013J"
    ids = np.arange(1, n + 1)
    eng = rng.beta(2, 2, n)  # engagement latent
    result = np.where(rng.rand(n) < (1 - eng) ** 1.3 * 0.9, np.where(rng.rand(n) < 0.5, "Withdrawn", "Fail"),
                      np.where(rng.rand(n) < 0.2, "Distinction", "Pass"))
    pd.DataFrame({"code_module": mod, "code_presentation": pres, "id_student": ids, "final_result": result}).to_csv(d / "studentInfo.csv", index=False)

    ass = pd.DataFrame({"code_module": mod, "code_presentation": pres, "id_assessment": [1, 2, 3, 4, 5],
                        "assessment_type": ["TMA"] * 4 + ["Exam"], "date": [20, 40, 60, 80, 240], "weight": [10, 20, 20, 20, 30]})
    ass.to_csv(d / "assessments.csv", index=False)

    sa = []
    for a, dt in zip([1, 2, 3, 4], [20, 40, 60, 80]):
        submit = rng.rand(n) < (0.3 + 0.7 * eng)
        score = np.clip(rng.normal(45 + 45 * eng, 12), 0, 100)
        for i in np.where(submit)[0]:
            sa.append((a, ids[i], dt + rng.randint(-3, 4), round(float(score[i]), 1)))
    pd.DataFrame(sa, columns=["id_assessment", "id_student", "date_submitted", "score"]).to_csv(d / "studentAssessment.csv", index=False)

    vle = []
    for i in range(n):
        days = np.unique(rng.randint(0, 100, rng.binomial(91, 0.05 + 0.6 * eng[i])))
        vle += [(mod, pres, ids[i], 1, int(day), int(rng.randint(1, 20))) for day in days]
    pd.DataFrame(vle, columns=["code_module", "code_presentation", "id_student", "id_site", "date", "sum_click"]).to_csv(d / "studentVle.csv", index=False)

    unreg = np.where((result == "Withdrawn") & (rng.rand(n) < 0.4), rng.randint(5, 80, n), np.nan)
    pd.DataFrame({"code_module": mod, "code_presentation": pres, "id_student": ids, "date_registration": -30, "date_unregistration": unreg}).to_csv(d / "studentRegistration.csv", index=False)
    return d


if __name__ == "__main__":
    print("ASSISTments synthétique :", make_assistments())
    print("OULAD synthétique       :", make_oulad())
