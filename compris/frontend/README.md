# Compris ? — frontend Angular

Interface à trois panneaux (façon NotebookLM), vierge au démarrage, état en mémoire uniquement.

## Parcours étudiant

1. **Import** : un ou plusieurs cours (PDF, Word, Excel, PowerPoint, texte), case à cocher par cours.
2. **Analyser** : le bouton en bas du panneau « Mes cours » marque la fin de l'import.
3. **Quiz** unité par unité, généré par l'agent à partir du cours.
4. L'étudiant répond à toutes les questions, puis envoie le quiz.
5. L'agent analyse les réponses et renvoie les **lacunes**.
6. Unité acquise → deux boutons : « Passer à l'unité suivante » ou « Poser des questions ou reformuler »
   (barre de questions, l'agent répond à partir du cours). Lacunes → « Poser des questions sur ces lacunes »
   ou « Refaire le quiz de l'unité ».

## Lancer

```bash
npm install
npm start          # http://localhost:4200
```

## Tester sans backend / brancher le backend

`src/app/core/config.ts` : `useMock: true` simule tout (3 unités de 3 questions ; bonnes réponses = choix 1, 2, 3 ;
unité acquise à partir de 2 bonnes réponses sur 3). Passe à `false` avec `apiUrl` vers FastAPI (CORS sur http://localhost:4200).

## Contrat d'API proposé (src/app/core/api.service.ts)

| Route | Envoi | Réponse |
|---|---|---|
| POST /upload | multipart, champ `file` | `{ course_id }` |
| POST /analyze | `{ course_ids }` | `{ units: [{ id, title, summary? }] }` |
| GET /quiz | `?course_id=a,b&unit_id=u1` | `{ questions: [{ id, question, choices, concept, level }] }` |
| POST /evaluate | `{ course_id, unit_id, answers: [{ question_id, answer }] }` (`answer` = index du choix) | `{ score, total, acquired, gaps: [{ concept, explanation }], feedback: [{ question_id, correct, explanation }] }` |
| POST /chat | `{ message, course_ids, unit_id }` | `{ reply, sources: [{ page, chapitre }], type }` (`in_course` / `out_of_course` / `off_topic`) |

## Structure

```
src/app/
  core/            config, modèles, ApiService, WorkspaceStore (signals)
  sources-panel/   import, cases à cocher, bouton Analyser
  stage-panel/     étude : accueil, analyse, quiz, résultat, fin de parcours
  chat-panel/      barre de questions (dans le panneau d'étude)
  journey-panel/   unités, avancement, lacunes
```
