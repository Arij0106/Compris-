import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { ApiService } from './api.service';
import {
  ACCEPTED_EXTENSIONS,
  ChatMessage,
  CourseSource,
  CourseUnit,
  Notice,
  QuizSession,
  Stage,
  UnitEvaluation,
  extOf,
  kindOf,
} from './models';

function uid(): string {
  return crypto.randomUUID();
}

function describeError(e: unknown): string {
  if (e instanceof HttpErrorResponse) {
    return e.status === 0 ? 'Serveur injoignable' : `Erreur serveur (${e.status})`;
  }
  return 'Échec de la requête';
}

/** Tout l'état de la page, en mémoire : rien n'est conservé au rechargement. */
@Injectable({ providedIn: 'root' })
export class WorkspaceStore {
  private readonly api = inject(ApiService);
  private readonly uploads = new Map<string, Subscription>();
  private journeySub: Subscription | undefined;
  private chatSub: Subscription | undefined;
  private noticeTimer: ReturnType<typeof setTimeout> | undefined;
  private retryFn: (() => void) | null = null;

  // Cours
  readonly sources = signal<CourseSource[]>([]);
  // Parcours
  readonly units = signal<CourseUnit[]>([]);
  readonly stage = signal<Stage>('idle');
  readonly unitIndex = signal(0);
  readonly quiz = signal<QuizSession | null>(null);
  readonly result = signal<UnitEvaluation | null>(null);
  readonly stageError = signal('');
  readonly analyzedIds = signal<string[]>([]);
  // Questions libres
  readonly chatOpen = signal(false);
  readonly messages = signal<ChatMessage[]>([]);
  readonly sending = signal(false);
  // Divers
  readonly notice = signal<Notice | null>(null);

  readonly eligible = computed(() => this.sources().filter((s) => s.status !== 'error'));
  readonly selectedCount = computed(() => this.eligible().filter((s) => s.selected).length);
  readonly allSelected = computed(
    () => this.eligible().length > 0 && this.selectedCount() === this.eligible().length,
  );
  readonly someSelected = computed(
    () => this.selectedCount() > 0 && this.selectedCount() < this.eligible().length,
  );
  readonly selectedReady = computed(() =>
    this.sources().filter((s) => s.selected && s.status === 'ready'),
  );
  readonly courseIds = computed(() =>
    this.selectedReady()
      .map((s) => s.courseId)
      .filter((id): id is string => !!id),
  );
  readonly uploading = computed(() => this.sources().some((s) => s.status === 'uploading'));
  readonly canAnalyze = computed(
    () => this.courseIds().length > 0 && !this.uploading() && this.stage() !== 'analyzing',
  );
  readonly hasAnalysis = computed(() => this.units().length > 0);
  readonly selectionChanged = computed(
    () => this.hasAnalysis() && this.analyzedIds().join(',') !== this.courseIds().join(','),
  );

  readonly currentUnit = computed(() => this.units()[this.unitIndex()] ?? null);
  readonly hasNextUnit = computed(() => this.unitIndex() + 1 < this.units().length);
  readonly allAnswered = computed(() => {
    const q = this.quiz();
    return !!q && q.answers.every((a) => a !== null);
  });
  readonly answeredCount = computed(() => this.quiz()?.answers.filter((a) => a !== null).length ?? 0);
  readonly acquiredCount = computed(() => this.units().filter((u) => u.status === 'acquired').length);
  readonly gaps = computed(() =>
    this.units().flatMap((u) => u.gaps.map((g) => ({ ...g, unit: u.title }))),
  );
  readonly isEmpty = computed(() => !this.sources().length && !this.units().length);

  // ---------- 1. Import des cours ----------

  addFiles(files: File[]): void {
    const rejected: string[] = [];
    const duplicates: string[] = [];
    let added = 0;

    for (const file of files) {
      const ext = extOf(file.name);
      if (!ACCEPTED_EXTENSIONS.includes(ext)) {
        rejected.push(file.name);
        continue;
      }
      if (this.sources().some((s) => s.name === file.name && s.size === file.size)) {
        duplicates.push(file.name);
        continue;
      }
      const source: CourseSource = {
        id: uid(),
        name: file.name,
        size: file.size,
        ext,
        kind: kindOf(ext),
        selected: true,
        status: 'uploading',
        progress: 0,
        file,
      };
      this.sources.update((l) => [...l, source]);
      this.startUpload(source);
      added++;
    }

    if (rejected.length) {
      this.say(
        'error',
        `Format non pris en charge : ${rejected.join(', ')}. Formats acceptés : PDF, Word, Excel, PowerPoint, texte.`,
      );
    } else if (duplicates.length && !added) {
      this.say('info', `Déjà ajouté : ${duplicates.join(', ')}.`);
    }
  }

  toggle(id: string): void {
    this.patch(id, { selected: !this.sources().find((s) => s.id === id)?.selected });
  }

  toggleAll(): void {
    const target = !this.allSelected();
    this.sources.update((l) =>
      l.map((s) => (s.status === 'error' ? s : { ...s, selected: target })),
    );
  }

  remove(id: string): void {
    this.uploads.get(id)?.unsubscribe();
    this.uploads.delete(id);
    this.sources.update((l) => l.filter((s) => s.id !== id));
  }

  retry(id: string): void {
    const source = this.sources().find((s) => s.id === id);
    if (source) {
      this.patch(id, { selected: true });
      this.startUpload(source);
    }
  }

  private startUpload(source: CourseSource): void {
    this.patch(source.id, { status: 'uploading', progress: 0, error: undefined });
    const sub = this.api.upload(source.file).subscribe({
      next: (u) =>
        u.courseId
          ? this.patch(source.id, { status: 'ready', progress: 100, courseId: u.courseId })
          : this.patch(source.id, { progress: u.progress }),
      error: (e: unknown) => {
        this.uploads.delete(source.id);
        this.patch(source.id, { status: 'error', selected: false, error: describeError(e) });
      },
      complete: () => {
        this.uploads.delete(source.id);
        if (this.sources().find((s) => s.id === source.id)?.status === 'uploading') {
          this.patch(source.id, {
            status: 'error',
            selected: false,
            error: 'Réponse inattendue du serveur',
          });
        }
      },
    });
    this.uploads.set(source.id, sub);
  }

  private patch(id: string, p: Partial<CourseSource>): void {
    this.sources.update((l) => l.map((s) => (s.id === id ? { ...s, ...p } : s)));
  }

  // ---------- 2. Analyse des cours (fin de l'import) ----------

  analyze(): void {
    if (!this.canAnalyze()) return;
    this.stopJourney();
    this.chatOpen.set(false);
    this.stage.set('analyzing');
    const ids = this.courseIds();
    // Fix #10 : mémoriser les unités déjà traitées pour ne pas écraser les acquis
    const prevUnits = new Map(this.units().map((u) => [u.id, u]));

    this.journeySub = this.api.analyze(ids).subscribe({
      next: (r) => {
        if (!r.units.length) {
          this.stage.set('idle');
          this.say('info', 'Aucune unité détectée dans ces cours.');
          return;
        }
        this.analyzedIds.set(ids);
        // Fix #10 : fusionner les nouvelles unités avec celles déjà complétées
        const mergedUnits: CourseUnit[] = r.units.map((u) => {
          const prev = prevUnits.get(u.id);
          if (prev && (prev.status === 'acquired' || prev.status === 'gaps')) {
            return {
              ...u,
              status: prev.status,
              score: prev.score,
              total: prev.total,
              gaps: prev.gaps,
            };
          }
          return { ...u, status: 'todo', gaps: [] };
        });
        this.units.set(mergedUnits);

        // Se positionner sur la première unité non encore acquise
        const firstPending = mergedUnits.findIndex((u) => u.status !== 'acquired');
        const targetIndex = firstPending >= 0 ? firstPending : 0;
        this.startUnit(targetIndex);
      },
      error: (e: unknown) =>
        this.fail(`Analyse impossible : ${describeError(e)}.`, () => this.analyze()),
    });
  }

  cancelAnalysis(): void {
    this.stopJourney();
    this.stage.set('idle');
  }

  // ---------- 3. Quiz d'une unité ----------

  private startUnit(i: number): void {
    this.journeySub?.unsubscribe();
    this.unitIndex.set(i);
    this.chatOpen.set(false);
    this.result.set(null);
    this.quiz.set(null);
    this.setUnit(i, { status: 'current', gaps: [], score: undefined, total: undefined });
    this.stage.set('quizLoading');

    const unit = this.units()[i];
    this.journeySub = this.api.quiz(this.analyzedIds(), unit.id).subscribe({
      next: (questions) => {
        if (!questions.length) {
          this.fail('Le serveur n’a renvoyé aucune question pour cette unité.', () => this.startUnit(i));
          return;
        }
        this.quiz.set({ questions, answers: questions.map(() => null), index: 0 });
        this.stage.set('quiz');
      },
      error: (e: unknown) =>
        this.fail(`Quiz indisponible : ${describeError(e)}.`, () => this.startUnit(i)),
    });
  }

  pick(choice: number): void {
    this.quiz.update(
      (q) => q && { ...q, answers: q.answers.map((a, i) => (i === q.index ? choice : a)) },
    );
  }

  nextQuestion(): void {
    this.quiz.update((q) => q && { ...q, index: Math.min(q.index + 1, q.questions.length - 1) });
  }

  prevQuestion(): void {
    this.quiz.update((q) => q && { ...q, index: Math.max(q.index - 1, 0) });
  }

  // ---------- 4-5. Réponses et analyse des lacunes ----------

  submitQuiz(): void {
    const q = this.quiz();
    const unit = this.currentUnit();
    if (!q || !unit || !this.allAnswered()) return;

    this.stage.set('evaluating');
    const answers = q.questions.map((question, i) => ({
      question_id: question.id,
      answer: q.answers[i] as number,
    }));

    this.journeySub = this.api.evaluate(this.analyzedIds(), unit.id, answers).subscribe({
      next: (r) => {
        this.result.set(r);
        this.setUnit(this.unitIndex(), {
          status: r.acquired ? 'acquired' : 'gaps',
          score: r.score,
          total: r.total,
          gaps: r.gaps,
        });
        this.stage.set('result');
      },
      error: (e: unknown) =>
        this.fail(`Analyse des réponses impossible : ${describeError(e)}.`, () => this.submitQuiz()),
    });
  }

  // ---------- 6. Suite du parcours ----------

  nextUnit(): void {
    if (this.hasNextUnit()) {
      this.startUnit(this.unitIndex() + 1);
    } else {
      this.chatOpen.set(false);
      this.quiz.set(null);
      this.result.set(null);
      this.stage.set('finished');
    }
  }

  retryUnit(): void {
    this.startUnit(this.unitIndex());
  }

  // Fix #9 : permettre le retour à n'importe quelle unité (y compris les quiz déjà traités)
  goToUnit(index: number): void {
    const unit = this.units()[index];
    if (!unit || this.stage() === 'analyzing' || this.stage() === 'evaluating') return;
    this.startUnit(index);
  }

  restartJourney(): void {
    this.units.update((l) => l.map((u) => ({ ...u, status: 'todo', gaps: [], score: undefined, total: undefined })));
    this.startUnit(0);
  }

  retryStage(): void {
    this.retryFn?.();
  }

  openChat(): void {
    this.chatOpen.set(true);
  }

  closeChat(): void {
    this.chatOpen.set(false);
  }

  send(text: string): void {
    const message = text.trim();
    const ids = this.analyzedIds();
    if (!message || this.sending() || !ids.length) return;

    this.messages.update((l) => [...l, { id: uid(), role: 'user', text: message }]);
    this.sending.set(true);

    this.chatSub = this.api.chat(message, ids, this.currentUnit()?.id).subscribe({
      next: (r) => {
        this.messages.update((l) => [
          ...l,
          { id: uid(), role: 'tutor', text: r.reply, sources: r.sources, type: r.type },
        ]);
        this.sending.set(false);
      },
      error: (e: unknown) => {
        this.messages.update((l) => [
          ...l,
          { id: uid(), role: 'tutor', text: `${describeError(e)}. Réessaie dans un instant.`, failed: true },
        ]);
        this.sending.set(false);
      },
    });
  }

  // ---------- Session ----------

  reset(): void {
    this.uploads.forEach((s) => s.unsubscribe());
    this.uploads.clear();
    this.stopJourney();
    this.sources.set([]);
    this.messages.set([]);
    this.units.set([]);
    this.analyzedIds.set([]);
    this.chatOpen.set(false);
    this.notice.set(null);
  }

  dismissNotice(): void {
    clearTimeout(this.noticeTimer);
    this.notice.set(null);
  }

  private stopJourney(): void {
    this.journeySub?.unsubscribe();
    this.chatSub?.unsubscribe();
    this.sending.set(false);
    this.quiz.set(null);
    this.result.set(null);
    this.unitIndex.set(0);
    this.retryFn = null;
    this.stage.set('idle');
  }

  private setUnit(i: number, p: Partial<CourseUnit>): void {
    this.units.update((l) => l.map((u, idx) => (idx === i ? { ...u, ...p } : u)));
  }

  private fail(message: string, retry: () => void): void {
    this.stageError.set(message);
    this.retryFn = retry;
    this.stage.set('error');
  }

  private say(kind: Notice['kind'], text: string): void {
    clearTimeout(this.noticeTimer);
    this.notice.set({ kind, text });
    this.noticeTimer = setTimeout(() => this.notice.set(null), 6000);
  }
}
