import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ACCEPT_ATTR } from '../core/models';
import { WorkspaceStore } from '../core/workspace.store';

@Component({
  selector: 'app-sources-panel',
  templateUrl: './sources-panel.html',
  styleUrl: './sources-panel.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SourcesPanel {
  protected readonly store = inject(WorkspaceStore);
  protected readonly accept = ACCEPT_ATTR;
  protected readonly dragging = signal(false);

  protected onPick(input: HTMLInputElement): void {
    this.store.addFiles(Array.from(input.files ?? []));
    input.value = '';
  }

  protected onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(true);
  }

  protected onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(false);
    this.store.addFiles(Array.from(event.dataTransfer?.files ?? []));
  }

  protected analyze(): void {
    if (
      this.store.hasAnalysis() &&
      !confirm('Relancer l’analyse ? Ta progression dans les unités sera réinitialisée.')
    ) {
      return;
    }
    this.store.analyze();
  }

  protected size(bytes: number): string {
    if (bytes < 1024) return `${bytes} o`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} Ko`;
    return `${(bytes / 1024 / 1024).toFixed(1).replace('.', ',')} Mo`;
  }
}
