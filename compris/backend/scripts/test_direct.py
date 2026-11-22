"""Direct integration test calling router logic with real database and ML models."""
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from starlette.datastructures import UploadFile as StarletteUploadFile
from app.database import SessionLocal, init_db
from app.routers import chat, courses, learning, teacher
from app.schemas import AnalyzeIn, ChatIn, EvaluateIn, QuizAnswerItem
from fastapi import BackgroundTasks

def main():
    print("=" * 60)
    print("Test direct de tous les services Backend, ML et Tuteur LLM")
    print("=" * 60)

    init_db()
    db = SessionLocal()

    try:
        # 1. Health
        print("\n[1] Test /health...")
        h = teacher.health()
        print(f"  ✅ Health: {h}")
        assert h["status"] == "ok"
        assert h["dropout_model"] is True, "Modèle de décrochage doit être présent"

        # 2. Metrics
        print("\n[2] Test /ml/metrics...")
        m = teacher.ml_metrics()
        print(f"  ✅ ML Metrics: Dropout AUC = {m['dropout']['auc']}, KT AUC = {m['knowledge_tracing']['auc_bkt']}")

        # 3. Course Upload & Ingestion
        print("\n[3] Test Upload d'un cours...")
        content = (
            "Chapitre 1 — Introduction aux Algorithmes\n\n"
            "Un algorithme est une suite ordonnée d'instructions permettant de résoudre un problème précis. "
            "La complexité temporelle mesure le nombre d'opérations élémentaires en fonction de la taille n des données. "
            "La notation Grand-O, notée O(n), permet de classifier le comportement asymptotique d'un algorithme.\n\n"
            "Chapitre 2 — Structures de Données Élémentaires\n\n"
            "Une pile est une structure de données de type LIFO (Last In First Out), où le dernier élément inséré est le premier retiré. "
            "Une file est une structure de type FIFO (First In First Out), où le premier arrivé est le premier servi. "
            "Les arbres binaires de recherche permettent d'effectuer des recherches efficaces en O(log n)."
        )
        bio = io.BytesIO(content.encode("utf-8"))
        upload_file = StarletteUploadFile(file=bio, filename="cours_algo.txt")
        bg = BackgroundTasks()
        up = courses.upload(background=bg, file=upload_file, title="Algorithmique et Structures", language="fr", db=db)
        course_id = up["course_id"]
        print(f"  ✅ Cours créé : ID={course_id}, Titre={up['title']}")
        print(f"  ✅ Chapitres : {[c['title'] for c in up['chapters']]}")
        print(f"  ✅ Concepts : {[c['name'] for c in up['concepts']]}")

        # 4. Analyze (pour le Frontend)
        print("\n[4] Test /analyze...")
        an = courses.analyze(AnalyzeIn(course_ids=[course_id]), db=db)
        units = an.get("units", [])
        print(f"  ✅ {len(units)} unités créées pour le parcours étudiant :")
        for u in units:
            print(f"     - [{u['id']}] {u['title']}")
        assert len(units) >= 1
        unit_id = units[0]["id"]

        # 5. Quiz pour l'unité (pour le Frontend)
        print(f"\n[5] Test /quiz pour l'unité {unit_id}...")
        qz = learning.quiz(course_id=str(course_id), unit_id=str(unit_id), n=3, db=db)
        questions = qz.get("questions", [])
        print(f"  ✅ {len(questions)} questions renvoyées :")
        for q in questions:
            print(f"     - [{q['id']}] {q['question'][:55]}... [Niveau: {q['level']}]")
            assert "choices" in q and len(q["choices"]) > 1
        assert len(questions) > 0
        q1 = questions[0]

        # 6. Evaluate (pour le Frontend)
        print("\n[6] Test /evaluate...")
        ev = learning.evaluate(
            EvaluateIn(
                course_id=str(course_id),
                unit_id=str(unit_id),
                answers=[QuizAnswerItem(question_id=str(q1["id"]), answer=0)],
                student_id="etudiant_demo",
            ),
            db=db,
        )
        print(f"  ✅ Résultat évaluation : Score = {ev['score']}/{ev['total']}, Acquis = {ev['acquired']}")
        print(f"  ✅ Feedback : {ev['feedback']}")
        print(f"  ✅ Lacunes : {ev['gaps']}")

        # 7. Chat : Salutation polie
        print("\n[7] Test Chat : Salutation polie...")
        c1 = chat.chat(ChatIn(message="Bonjour !", course_ids=[course_id]), db=db)
        print(f"  ✅ Réponse salutation : {c1['reply']}")
        assert "bonjour" in c1["reply"].lower() or "tuteur" in c1["reply"].lower()

        # 8. Chat : Demande hors études (météo / jeux / sports) -> Refus poli et réorientation
        print("\n[8] Test Chat : Demande hors études (« Quel temps fait-il et qui a gagné le match de foot ? »)...")
        c2 = chat.chat(ChatIn(message="Quel temps fait-il et qui a gagné le match de foot ?", course_ids=[course_id]), db=db)
        print(f"  ✅ Réponse tuteur (déclin poli) :\n« {c2['reply']} »")
        assert c2["type"] == "off_topic"
        assert "cours" in c2["reply"].lower() or "étude" in c2["reply"].lower()

        # 9. Chat : Autre demande hors études (blague) -> Refus poli et réorientation
        print("\n[9] Test Chat : Demande de blague...")
        c3 = chat.chat(ChatIn(message="Raconte-moi une blague", course_ids=[course_id]), db=db)
        print(f"  ✅ Réponse blague (déclin poli) :\n« {c3['reply']} »")
        assert c3["type"] == "off_topic"

        # 10. Chat : Question d'étude sur le cours
        print("\n[10] Test Chat : Question d'étude sur le cours (« Explique-moi la complexité d'un algorithme »)...")
        c4 = chat.chat(ChatIn(message="Explique-moi la complexité d'un algorithme", course_ids=[course_id]), db=db)
        print(f"  ✅ Réponse pédagogique socratique :\n« {c4['reply']} »")
        print(f"  ✅ Sources citées : {c4['sources']}")
        assert c4["type"] in ("in_course", "out_of_course")

        print("\n" + "=" * 60)
        print("🎉 TOUS LES TESTS D'INTÉGRATION ET GARDE-FOUS SONT VALIDÉS AVEC SUCCÈS !")
        print("=" * 60)

    finally:
        db.close()

if __name__ == "__main__":
    main()
