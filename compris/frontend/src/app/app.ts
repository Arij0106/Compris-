import { ChangeDetectionStrategy, Component, effect, inject, signal } from '@angular/core';
import { APP_CONFIG } from './core/config';
import { WorkspaceStore } from './core/workspace.store';
import { JourneyPanel } from './journey-panel/journey-panel';
import { SourcesPanel } from './sources-panel/sources-panel';
import { StagePanel } from './stage-panel/stage-panel';

type View = 'sources' | 'stage' | 'journey';

@Component({
  selector: 'app-root',
  imports: [SourcesPanel, StagePanel, JourneyPanel],
  templateUrl: './app.html',
  styleUrl: './app.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  protected readonly store = inject(WorkspaceStore);
  protected readonly demo = APP_CONFIG.useMock;
  protected readonly apiUrl = APP_CONFIG.apiUrl;
  protected readonly view = signal<View>('sources');

  protected readonly views: { id: View; label: string }[] = [
    { id: 'sources', label: 'Cours' },
    { id: 'stage', label: 'Étude' },
    { id: 'journey', label: 'Unités' },
  ];

  constructor() {
    // Sur mobile, bascule vers l'étude dès que l'analyse démarre.
    effect(() => {
      if (this.store.stage() === 'analyzing') this.view.set('stage');
    });
  }

  protected reset(): void {
    if (confirm('Vider la session ? Les cours, la conversation et les résultats seront effacés.')) {
      this.store.reset();
    }
  }
}
