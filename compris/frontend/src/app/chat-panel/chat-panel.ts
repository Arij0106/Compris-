import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { WorkspaceStore } from '../core/workspace.store';

/** Fil de questions libres : l'agent répond à partir du cours. */
@Component({
  selector: 'app-chat-panel',
  templateUrl: './chat-panel.html',
  styleUrl: './chat-panel.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChatPanel {
  protected readonly store = inject(WorkspaceStore);
  protected readonly draft = signal('');

  private readonly stream = viewChild<ElementRef<HTMLElement>>('stream');
  private readonly input = viewChild<ElementRef<HTMLTextAreaElement>>('input');

  protected readonly starters = computed(() => {
    const gaps = this.store.currentUnit()?.gaps ?? [];
    return [
      ...gaps.slice(0, 2).map((g) => `Explique-moi « ${g.concept} » autrement`),
      'Reformule le point principal de cette unité',
      'Donne-moi un exemple tiré du cours',
    ];
  });

  protected readonly canSend = computed(() => !!this.draft().trim() && !this.store.sending());

  constructor() {
    effect(() => {
      this.store.messages();
      this.store.sending();
      setTimeout(() => {
        const el = this.stream()?.nativeElement;
        el?.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
      });
    });
    setTimeout(() => this.input()?.nativeElement.focus());
  }

  protected onInput(el: HTMLTextAreaElement): void {
    this.draft.set(el.value);
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  protected onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      this.submit();
    }
  }

  protected submit(): void {
    if (!this.canSend()) return;
    this.store.send(this.draft());
    this.draft.set('');
    const el = this.input()?.nativeElement;
    if (el) el.style.height = 'auto';
  }

  protected useStarter(text: string): void {
    this.draft.set(text);
    this.input()?.nativeElement.focus();
  }
}
