"""Vérification automatique de l'installation des datasets, de la configuration et des dépendances."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml import config as cfg

def main():
    print("=" * 60)
    print("Vérification de l'installation et des datasets du Backend")
    print("=" * 60)

    # 1. Vérification ASSISTments
    print("\n[1] Vérification ASSISTments (Knowledge Tracing)...")
    assist_p = cfg.ASSISTMENTS_PATH
    print(f"Chemin résolu : {assist_p}")
    if not assist_p.exists():
        print(f"  ❌ ERREUR : fichier ASSISTments introuvable à {assist_p}")
    else:
        print(f"  ✅ Fichier trouvé ({assist_p.stat().st_size / (1024*1024):.1f} Mo)")
        with open(assist_p, "r", encoding=cfg.KT_ENCODING, errors="replace") as f:
            reader = csv.reader(f)
            header = next(reader)
            needed = [cfg.KT_USER_COL, cfg.KT_CORRECT_COL, cfg.KT_ORDER_COL]
            skill_ok = cfg.KT_SKILL_COL in header or "skill_name" in header
            missing = [c for c in needed if c not in header]
            if missing or not skill_ok:
                print(f"  ❌ Colonnes manquantes dans ASSISTments : {missing} (skill ok: {skill_ok})")
            else:
                print(f"  ✅ Colonnes validées : {cfg.KT_USER_COL}, {cfg.KT_SKILL_COL}, {cfg.KT_CORRECT_COL}, {cfg.KT_ORDER_COL}")

    # 2. Vérification OULAD
    print("\n[2] Vérification OULAD (Prédiction de décrochage)...")
    oulad_d = cfg.OULAD_DIR
    print(f"Dossier résolu : {oulad_d}")
    required_oulad = ["studentInfo.csv", "assessments.csv", "studentAssessment.csv", "studentVle.csv"]
    optional_oulad = ["studentRegistration.csv", "courses.csv", "vle.csv"]
    
    missing_req = []
    for f in required_oulad:
        p = oulad_d / f
        if p.exists():
            print(f"  ✅ {f} trouvé ({p.stat().st_size / (1024*1024):.2f} Mo)")
        else:
            print(f"  ❌ {f} MANQUANT")
            missing_req.append(f)
            
    for f in optional_oulad:
        p = oulad_d / f
        if p.exists():
            print(f"  ℹ️  {f} trouvé (recommandé/optionnel, {p.stat().st_size / (1024*1024):.2f} Mo)")
        else:
            print(f"  ⚠️  {f} absent")

    # 3. Vérification des dossiers
    print("\n[3] Vérification de l'arborescence...")
    for d in [ROOT / "models", ROOT / "storage", ROOT / "storage" / "uploads"]:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  ✅ Dossier présent : {d.relative_to(ROOT)}")

    # Résumé
    print("\n" + "=" * 60)
    if not assist_p.exists() or missing_req:
        print("❌ Certaines vérifications ont échoué. Corrigez les points ci-dessus.")
        return 1
    else:
        print("✅ TOUT EST PRÊT ! Vos datasets sont bien placés et prêts pour l'entraînement.")
        print("Commandes pour entraîner :")
        print("  - Avec Docker : docker compose run --rm backend python -m ml.train_all")
        print("  - En local    : python -m ml.train_all")
        print("=" * 60)
        return 0

if __name__ == "__main__":
    sys.exit(main())
