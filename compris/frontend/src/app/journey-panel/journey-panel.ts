import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { UnitStatus } from '../core/models';
import { WorkspaceStore } from '../core/workspace.store';

@Component({
  selector: 'app-journey-panel',
  templateUrl: './journey-panel.html',
  styleUrl: './journey-panel.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class JourneyPanel {
  protected readonly store = inject(WorkspaceStore);

  protected label(status: UnitStatus): string {
    switch (status) {
      case 'current': return 'En cours';
      case 'acquired': return 'Acquise';
      case 'gaps': return 'Lacunes';
      default: return 'À faire';
    }
  }
}
