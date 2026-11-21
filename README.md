# Maieutic
Tuteur IA socratique : diagnostique les lacunes de compréhension à partir du cours de l'étudiant (RAG), le guide par indices progressifs, suit sa maîtrise par concept et planifie ses révisions espacées.
Le problème

Les étudiants ne disent pas qu'ils ne comprennent pas. Ils ont des lacunes cachées (prérequis manquants, conceptions erronées) que ni le cours ni les chatbots classiques ne détectent. Un chatbot qui donne la réponse améliore la note à court terme, mais détruit l'apprentissage.

Selon le problème des deux sigmas de Bloom (1984), un élève avec un tuteur individuel performe environ 2 écarts-types au-dessus de l'enseignement classique. Maieutic vise à rendre ce tutorat accessible à tous.

La solution
Upload d'un cours (PDF/PPT).
Diagnostic adaptatif : 5 à 8 questions qui révèlent les prérequis manquants.
Tuteur socratique : indices graduels, jamais la solution d'emblée.
Carte de maîtrise par concept (vert / orange / rouge), mise à jour en temps réel.
Révisions espacées planifiées automatiquement.
Fonctionnalités
Fonctionnalité	Fondement pédagogique
Indices progressifs, pas de réponse directe	Zone proximale de développement (Vygotsky), échafaudage (Bruner)
Questions de relance socratiques	Maïeutique, apprentissage actif
Quiz courts de rappel	Effet de test / retrieval practice (Roediger & Karpicke)
Révisions espacées	Courbe de l'oubli (Ebbinghaus), répétition espacée
Détection des prérequis manquants	Graphe de connaissances, apprentissage par maîtrise (Bloom)
Niveaux de questions (retenir → analyser → créer)	Taxonomie de Bloom révisée
Explications par analogie, schéma, exemple	Charge cognitive (Sweller), double codage (Paivio)
Feedback immédiat et formatif	Feedback formatif (Hattie)
Mode « explique-moi avec tes mots »	Effet Feynman / auto-explication
Architecture
Cours de l'étudiant (PDF/PPT)
        ↓ extraction + découpage
Base vectorielle (RAG)  ←→  Graphe de concepts / prérequis
        ↓
┌──────────────────────────────────────────┐
│ Agent tuteur (LLM)                       │
│ 1. Diagnostic : quiz adaptatif           │
│ 2. Tuteur socratique : indices graduels  │
│ 3. Explications multi-formats            │
│ 4. Générateur de quiz / flashcards       │
└──────────────────────────────────────────┘
        ↓
Modèle de suivi de maîtrise (knowledge tracing)
        ↓
Planificateur de révision espacée + tableau de bord
Stack technique
Couche	Technologie
Frontend	Application web (dossier frontend/) — à compléter : Angular / React…
Backend	Python, API REST (dossier backend/)
IA	API LLM + RAG (réponses qui citent la page du cours)
Base vectorielle	Chroma
Suivi de maîtrise	Knowledge tracing (BKT / DKT léger)
Révision espacée	Algorithme type SM-2 / FSRS
Conteneurisation	Docker / Docker Compose
Données et validation

Le modèle de suivi de maîtrise est validé sur un jeu de données public, avec métriques affichées (AUC, précision).

Usage	Dataset
Knowledge tracing	ASSISTments, EdNet, Junyi Academy, Statics2011
Détection de conceptions erronées	ASAP-SAS / ASAP-AES, SciEntsBank, Beetle
Génération de questions	SQuAD, RACE, SciQ
Prédiction du décrochage	OULAD

Dataset utilisé dans ce dépôt : à compléter (nom, version, métriques obtenues).

Les cours réels des étudiants (PDF, y compris en français et arabe) servent de base au RAG.

Structure du dépôt
.
├── frontend/            # Interface web
├── backend/             # API, RAG, tuteur, knowledge tracing
├── docs/                # Captures, schémas, slides du pitch
├── docker-compose.yml   # Lance l'ensemble
├── .env.example         # Variables d'environnement à copier en .env
├── .gitignore
├── LICENSE
└── README.md
Installation
Prérequis
Git
Docker et Docker Compose (ou Python 3.11+ et Node.js 20+ pour un lancement manuel)
Une clé d'API pour le LLM utilisé
1. Cloner le dépôt
bash
git clone https://github.com/TON_USER/TON_REPO.git
cd TON_REPO
2. Configurer l'environnement
bash
cp .env.example .env      # Windows : copy .env.example .env

Renseigne ensuite tes clés dans .env. Ne commit jamais ce fichier.

3. Lancer avec Docker
bash
docker compose up --build
Frontend : http://localhost:4200
Backend : http://localhost:8000
Documentation de l'API : http://localhost:8000/docs
Lancement manuel (sans Docker)
bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate          # Linux/Mac : source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (dans un autre terminal)
cd frontend
npm install
npm start

Adapte les commandes et les ports à ta configuration réelle.

Éthique et accessibilité
Pas de triche : l'IA ne rend pas les devoirs, elle guide.
Données privées : les cours et les progrès de l'étudiant restent confidentiels.
Transparence sur les limites de l'IA.
Accessibilité : français, arabe, police adaptée à la dyslexie.
Impact durable
Rétention à long terme grâce à la répétition espacée.
Autonomie : l'étudiant apprend à apprendre, il ne dépend pas de l'IA.
Déploiement possible dans une école ou une faculté.
Évaluation

Mini-expérience prévue : pré-test / post-test sur un même chapitre avec 5 à 10 étudiants.

Métrique	Résultat
Taux de bonnes réponses avant → après	à compléter
AUC du modèle de suivi (dataset)	à compléter
Satisfaction	à compléter
Feuille de route
[x] Upload d'un cours → RAG → tuteur socratique
[x] Quiz de diagnostic
[ ] Carte de maîtrise par concept
[ ] Révision espacée automatique
[ ] Modèle validé sur dataset réel avec métriques
[ ] Mode Feynman, support de l'arabe, rappels par e-mail

(Coche ce qui est réellement terminé.)

Équipe
Nom	Rôle
à compléter	Frontend
à compléter	Backend / IA
