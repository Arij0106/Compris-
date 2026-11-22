"""End-to-end integration test verifying all backend endpoints, ML models, and LLM guardrails."""
import asyncio
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx
from app.database import init_db
from app.main import app


async def run_async_tests():
    print("=" * 60)
    print("Lancement des tests d'intégration Backend + Frontend + LLM")
    print("=" * 60)

    init_db()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
        # 1. Health & Models Check
        print("\n[1] Test GET /health...")
        r = await client.get("/health")
        assert r.status_code == 200, f"Health check failed: {r.text}"
        health = r.json()
        print(f"  ✅ Health response: {health}")
        assert health["status"] == "ok"
        assert health["dropout_model"] is True, "Le modèle de décrochage (OULAD) doit être chargé !"

        # 2. ML Metrics Check
        print("\n[2] Test GET /ml/metrics...")
        r = await client.get("/ml/metrics")
        assert r.status_code == 200, f"Metrics failed: {r.text}"
        metrics = r.json()
        assert "dropout" in metrics, "Métriques de décrochage manquantes"
        assert "knowledge_tracing" in metrics, "Métriques de Knowledge Tracing manquantes"
        print(f"  ✅ Métriques validées : AUC Dropout = {metrics['dropout']['auc']}, AUC KT = {metrics['knowledge_tracing']['auc_bkt']}")

        # 3. Test Course Upload
        print("\n[3] Test POST /upload (cours exemple)...")
        sample_course_content = (
            "Chapitre 1 — Introduction aux Algorithmes\n\n"
            "Un algorithme est une suite ordonnée d'instructions permettant de résoudre un problème précis. "
            "La complexité temporelle mesure le nombre d'opérations élémentaires en fonction de la taille n des données. "
            "La notation Grand-O, notée O(n), permet de classifier le comportement asymptotique d'un algorithme.\n\n"
            "Chapitre 2 — Structures de Données Élémentaires\n\n"
            "Une pile est une structure de données de type LIFO (Last In First Out), où le dernier élément inséré est le premier retiré. "
            "Une file est une structure de type FIFO (First In First Out), où le premier arrivé est le premier servi. "
            "Les arbres binaires de recherche permettent d'effectuer des recherches efficaces en O(log n)."
        )
        files = {"file": ("cours_algo.txt", io.BytesIO(sample_course_content.encode("utf-8")), "text/plain")}
        r = await client.post("/upload", files=files, data={"title": "Algorithmique et Complexité"})
        assert r.status_code == 200, f"Upload failed: {r.text}"
        upload_res = r.json()
        course_id = upload_res["course_id"]
        print(f"  ✅ Cours uploadé : ID {course_id}, Titre : « {upload_res['title']} »")
        print(f"  ✅ Chapitres détectés : {[c['title'] for c in upload_res['chapters']]}")
        print(f"  ✅ Concepts extraits : {[c['name'] for c in upload_res['concepts']]}")

        # 4. Test POST /analyze (Contrat Frontend)
        print("\n[4] Test POST /analyze (utilisé par le composant de parcours)...")
        r = await client.post("/analyze", json={"course_ids": [course_id]})
        assert r.status_code == 200, f"Analyze failed: {r.text}"
        units = r.json().get("units", [])
        assert len(units) >= 1, "Au moins une unité doit être analysée"
        print(f"  ✅ {len(units)} unités d'apprentissage générées :")
        for u in units:
            print(f"     - [{u['id']}] {u['title']} ({u.get('summary')})")
        first_unit_id = units[0]["id"]

        # 5. Test GET /quiz (Contrat Frontend)
        print(f"\n[5] Test GET /quiz pour l'unité {first_unit_id}...")
        r = await client.get(f"/quiz?course_id={course_id}&unit_id={first_unit_id}&n=3")
        assert r.status_code == 200, f"Quiz failed: {r.text}"
        questions = r.json().get("questions", [])
        assert len(questions) > 0, "Le quiz doit contenir des questions"
        print(f"  ✅ {len(questions)} questions renvoyées pour le quiz :")
        for q in questions:
            assert "question" in q and "choices" in q and "level" in q
            print(f"     - Question {q['id']}: {q['question'][:50]}... [{q['level']}]")
        sample_question = questions[0]

        # 6. Test POST /evaluate (Contrat Frontend)
        print(f"\n[6] Test POST /evaluate pour l'unité {first_unit_id}...")
        eval_body = {
            "course_id": str(course_id),
            "unit_id": str(first_unit_id),
            "answers": [
                {"question_id": str(sample_question["id"]), "answer": 0}
            ],
            "student_id": "etudiant_test"
        }
        r = await client.post("/evaluate", json=eval_body)
        assert r.status_code == 200, f"Evaluate failed: {r.text}"
        eval_res = r.json()
        assert "score" in eval_res and "total" in eval_res and "acquired" in eval_res and "feedback" in eval_res
        print(f"  ✅ Évaluation réussie : Score {eval_res['score']}/{eval_res['total']}, Acquis : {eval_res['acquired']}")
        print(f"  ✅ Feedback questions : {eval_res['feedback']}")
        print(f"  ✅ Lacunes identifiées : {eval_res['gaps']}")

        # 7. Test POST /chat : Salutation polie
        print("\n[7] Test POST /chat : Salutation polie (« Bonjour »)...")
        r = await client.post("/chat", json={"message": "Bonjour !", "course_ids": [str(course_id)], "student_id": "etudiant_test"})
        assert r.status_code == 200, f"Chat greeting failed: {r.text}"
        chat_greet = r.json()
        print(f"  ✅ Réponse salutation : {chat_greet['reply']}")
        assert "bonjour" in chat_greet["reply"].lower() or "tuteur" in chat_greet["reply"].lower()

        # 8. Test POST /chat : Demande non liée aux études (météo, jeux, blague...) -> Refus poli & redirection
        print("\n[8] Test POST /chat : Demande hors études (« Quel temps fait-il aujourd'hui ? »)...")
        r = await client.post("/chat", json={"message": "Quel temps fait-il aujourd'hui et quel est le score du match de foot ?", "course_ids": [str(course_id)], "student_id": "etudiant_test"})
        assert r.status_code == 200, f"Chat off-topic failed: {r.text}"
        chat_off = r.json()
        print(f"  ✅ Réponse refus poli : {chat_off['reply']}")
        assert chat_off["type"] == "off_topic"
        reply_lower = chat_off["reply"].lower()
        assert ("cours" in reply_lower or "étude" in reply_lower or "apprentissage" in reply_lower), "Doit rediriger vers le cours !"
        assert ("plaisir" in reply_lower or "bonjour" in reply_lower or "exclusif" in reply_lower or "rôle" in reply_lower), "Doit être très poli et bienveillant !"

        # 9. Test POST /chat : Autre demande hors études (« Raconte-moi une blague »)...
        print("\n[9] Test POST /chat : Autre demande hors études (« Raconte-moi une blague »)...")
        r = await client.post("/chat", json={"message": "Raconte-moi une blague s'il te plaît", "course_ids": [str(course_id)], "student_id": "etudiant_test"})
        assert r.status_code == 200
        chat_joke = r.json()
        print(f"  ✅ Réponse refus poli blague : {chat_joke['reply']}")
        assert chat_joke["type"] == "off_topic"

        # 10. Test POST /chat : Question d'étude sur le cours
        print("\n[10] Test POST /chat : Question d'étude (« C'est quoi la complexité O(n) ? »)...")
        r = await client.post("/chat", json={"message": "C'est quoi la complexité asymptotique O(n) ?", "course_ids": [str(course_id)], "student_id": "etudiant_test"})
        assert r.status_code == 200
        chat_study = r.json()
        print(f"  ✅ Réponse tuteur socratique : {chat_study['reply']}")
        print(f"  ✅ Type : {chat_study['type']}, Sources : {chat_study['sources']}")
        assert chat_study["type"] in ("in_course", "out_of_course")
        if chat_study["sources"]:
            assert "page" in chat_study["sources"][0]
            assert "chapitre" in chat_study["sources"][0] or "chapter" in chat_study["sources"][0]

        print("\n" + "=" * 60)
        print("✅ TOUS LES TESTS D'INTÉGRATION ET GARDE-FOUS ONT RÉUSSI AVEC SUCCÈS !")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_async_tests())
