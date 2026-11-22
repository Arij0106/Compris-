"""Lance tous les entraînements.

  python -m ml.train_all              → vos vrais datasets (chemins du .env)
  python -m ml.train_all --synthetic  → faux datasets (test du pipeline uniquement)
  python -m ml.train_all --only kt|oulad
"""
import argparse
import sys
import traceback

from ml import config as cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--only", choices=["kt", "oulad"])
    args = ap.parse_args()

    kt_path, oulad_dir = None, None
    if args.synthetic:
        from ml import make_synthetic

        kt_path, oulad_dir = make_synthetic.make_assistments(), make_synthetic.make_oulad()
        print("⚠ Mode synthétique : les métriques ne sont PAS des résultats réels.")

    failures = 0
    if args.only in (None, "kt"):
        from ml import train_kt

        try:
            train_kt.run(kt_path)
        except Exception as e:
            print(f"[KT] ERREUR: {e}")
            traceback.print_exc()
            failures += 1
    if args.only in (None, "oulad"):
        from ml import train_oulad

        try:
            train_oulad.run(oulad_dir)
        except Exception as e:
            print(f"[OULAD] ERREUR: {e}")
            traceback.print_exc()
            failures += 1
    print(f"\nTerminé. Modèles dans {cfg.MODELS_DIR}. Redémarrez l'API pour les charger : docker compose restart backend")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
