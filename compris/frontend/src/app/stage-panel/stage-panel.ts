import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { QuestionFeedback } from '../core/models';
import { WorkspaceStore } from '../core/workspace.store';
import { ChatPanel } from '../chat-panel/chat-panel';

@Component({
  selector: 'app-stage-panel',
  imports: [ChatPanel],
  templateUrl: './stage-panel.html',
  styleUrl: './stage-panel.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StagePanel {
  protected readonly store = inject(WorkspaceStore);

  protected readonly steps = computed(() => [
    { label: 'Importe tes cours', done: this.store.selectedReady().length > 0 },
    { label: 'Appuie sur « Analyser » quand l’import est terminé', done: this.store.hasAnalysis() },
    { label: 'Réponds aux quiz, unité par unité', done: this.store.acquiredCount() > 0 },
  ]);

  protected readonly backLabel = computed(() =>
    this.store.stage() === 'result' ? 'Retour au résultat' : 'Retour au parcours',
  );

  protected readonly quizProgress = computed(() => {
    const q = this.store.quiz();
    return q ? (this.store.answeredCount() / q.questions.length) * 100 : 0;
  });

  protected feedbackFor(id: string): QuestionFeedback | undefined {
    return this.store.result()?.feedback.find((f) => f.question_id === id);
  }
}
