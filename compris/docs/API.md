# Contrat d’API

Documentation interactive générée : `http://localhost:8000/docs`.

| Route | Corps / paramètres | Réponse |
|---|---|---|
| `POST /upload` | multipart : `file` (pdf, pptx, txt, md), `title?`, `language?` (fr, ar, en) | `{course_id, chapters, concepts, questions_status}` |
| `POST /analyze` | `{course_ids}` | `{units:[{id, title, summary?}]}` |
| `GET /courses` · `GET /courses/{id}` | | liste / détail + `questions_status` (`pending`, `running`, `ready`, `error`) |
| `GET /quiz` | `course_id`, `unit_id?`, `concept_id?`, `student_id?`, `n?` | `{questions, questions_status}` |
| `POST /evaluate` | `{course_id, unit_id, answers:[{question_id, answer}]}` | `{score, total, acquired, gaps, feedback}` |
| `POST /answer` | `{student_id, question_id, choice_index, time_spent?}` | `{correct, correct_index, explanation, next_question_id, mastery}` |
| `GET /profile` | `student_id`, `course_id?` | `{concepts, global_risk, global_risk_score}` |
| `POST /chat` | `{student_id, course_id, message, history?, hint_level?, mode?}` | `{reply, sources, type, next_hint_level?}` |
| `GET /review` | `student_id`, `course_id?` | `{cards}` |
| `POST /review/grade` | `{student_id, card_id, quality 0-5}` | prochaine échéance SM-2 |
| `GET /teacher/dashboard` | `course_id` | `{class_mastery, at_risk_count, hardest_concepts, n_students}` |
| `GET /ml/metrics` · `GET /health` | | métriques ML · état (LLM actif, modèles chargés) |

## Notes

- `student_id` : chaîne libre, créée à la première utilisation.
- Après `/upload`, interroger `GET /courses/{id}` jusqu’à `questions_status == "ready"`.
- Les routes `/analyze` et `/evaluate` sont celles utilisées par le frontend ; `/answer` est l’API question par question.
- Types `/chat` : `in_course`, `out_of_course`, `off_topic`.
