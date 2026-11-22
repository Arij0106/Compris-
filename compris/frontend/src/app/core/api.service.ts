import { HttpClient, HttpEventType } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, delay, filter, map, of, take, timer } from 'rxjs';
import { APP_CONFIG } from './config';
import {
  AnalyzedUnit,
  ChatReply,
  QuizQuestion,
  UnitEvaluation,
  UploadUpdate,
} from './models';

/**
 * Un seul point d'entrée vers le backend (contrat PROPOSÉ, à aligner avec le backend) :
 *   POST /upload    (multipart, champ "file")          -> { course_id }
 *   POST /analyze   { course_ids }                     -> { units: [{ id, title, summary? }] }
 *   GET  /quiz      ?course_id=a,b&unit_id=u1          -> { questions: [{ id, question, choices, concept, level }] }
 *   POST /evaluate  { course_id, unit_id, answers:[{ question_id, answer }] }
 *                                                      -> { score, total, acquired, gaps:[{ concept, explanation }],
 *                                                           feedback:[{ question_id, correct, explanation }] }
 *   POST /chat      { message, course_ids, unit_id }   -> { reply, sources:[{ page, chapitre }], type }
 * Si le backend change un format, tout se corrige ici.
 */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = APP_CONFIG.apiUrl.replace(/\/$/, '');

  // Mode démo : bonnes réponses = choix 0, 1, 2 pour les questions 1, 2, 3 de chaque unité.
  private readonly mockCorrect = [0, 1, 2];

  upload(file: File): Observable<UploadUpdate> {
    if (APP_CONFIG.useMock) {
      return timer(0, 90).pipe(
        take(10),
        map((i) =>
          i < 9
            ? { progress: (i + 1) * 10 }
            : { progress: 100, courseId: `demo-${crypto.randomUUID()}` },
        ),
      );
    }
    const body = new FormData();
    body.append('file', file, file.name);
    return this.http
      .post<{ course_id: string }>(`${this.base}/upload`, body, {
        reportProgress: true,
        observe: 'events',
      })
      .pipe(
        map((e): UploadUpdate | null => {
          if (e.type === HttpEventType.UploadProgress) {
            return { progress: e.total ? Math.round((100 * e.loaded) / e.total) : 0 };
          }
          if (e.type === HttpEventType.Response) {
            const cid = e.body?.course_id !== undefined ? String(e.body.course_id) : undefined;
            return { progress: 100, courseId: cid };
          }
          return null;
        }),
        filter((u): u is UploadUpdate => u !== null),
      );
  }

  analyze(courseIds: string[]): Observable<{ units: AnalyzedUnit[] }> {
    if (APP_CONFIG.useMock) {
      return of({
        units: [1, 2, 3].map((n) => ({
          id: `u${n}`,
          title: `Unité ${n} (exemple)`,
          summary: 'Unité générée par le mode démo.',
        })),
      }).pipe(delay(2200));
    }
    return this.http.post<{ units: AnalyzedUnit[] }>(`${this.base}/analyze`, {
      course_ids: courseIds,
    });
  }

  quiz(courseIds: string[], unitId: string): Observable<QuizQuestion[]> {
    if (APP_CONFIG.useMock) {
      const levels = ['Retenir', 'Comprendre', 'Analyser'];
      return of(
        [0, 1, 2].map((i) => ({
          id: `${unitId}-q${i + 1}`,
          question: `Question d’exemple ${i + 1} de l’${unitId.replace('u', 'unité ')} (mode démo)`,
          choices: ['Réponse A', 'Réponse B', 'Réponse C'],
          concept: `Concept ${'ABC'[i]}`,
          level: levels[i],
        })),
      ).pipe(delay(600));
    }
    return this.http
      .get<{ questions: QuizQuestion[] }>(`${this.base}/quiz`, {
        params: { course_id: courseIds.join(','), unit_id: unitId },
      })
      .pipe(map((r) => r.questions));
  }

  evaluate(
    courseIds: string[],
    unitId: string,
    answers: { question_id: string; answer: number }[],
  ): Observable<UnitEvaluation> {
    if (APP_CONFIG.useMock) {
      const feedback = answers.map((a, i) => {
        const correct = a.answer === this.mockCorrect[i];
        return {
          question_id: a.question_id,
          correct,
          explanation: correct
            ? 'Bonne réponse (exemple du mode démo).'
            : `Indice : Cette réponse n'est pas exacte. Revoyez la notion clé de Concept ${'ABC'[i]} pour analyser la nuance et trouver la réponse par vous-même !`,
        };
      });
      const score = feedback.filter((f) => f.correct).length;
      const acquired = score >= 2;
      return of<UnitEvaluation>({
        score,
        total: feedback.length,
        acquired,
        synthesis: acquired
          ? '🎉 Synthèse de l\'unité : Bravo pour la validation de cette unité ! Retenez que ces notions fondamentales constituent le socle de compréhension nécessaire pour aborder les chapitres suivants en toute confiance.'
          : undefined,
        gaps: feedback
          .map((f, i) => ({ f, i }))
          .filter(({ f }) => !f.correct)
          .map(({ i }) => ({
            concept: `Concept ${'ABC'[i]}`,
            explanation: 'Notion à revoir dans le cours (exemple du mode démo).',
          })),
        feedback,
      }).pipe(delay(1400));
    }
    return this.http.post<UnitEvaluation>(`${this.base}/evaluate`, {
      course_id: courseIds.join(','),
      unit_id: unitId,
      answers,
    });
  }

  chat(message: string, courseIds: string[], unitId?: string): Observable<ChatReply> {
    if (APP_CONFIG.useMock) {
      return of<ChatReply>({
        reply:
          `Voici ce que je réponds à partir du cours : « ${message} »\n\n` +
          `(Réponse simulée : le backend n’est pas branché.)`,
        sources: [],
        type: 'in_course',
      }).pipe(delay(900));
    }
    return this.http.post<ChatReply>(`${this.base}/chat`, {
      message,
      course_ids: courseIds,
      unit_id: unitId,
    });
  }
}
