import { Component, computed, inject, signal } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';

interface Provider {
  provider: string;
  kind: string;
  models: string[];
}

interface Example {
  title: string;
  product: string;
}

interface Draft {
  status: 'ready' | 'needs_review' | 'needs_data' | 'error';
  name: string;
  seo_title: string;
  seo_description: string;
  key_specs: { name: string; value: string }[];
  search_queries: string[];
  query_stats: { query: string; frequency: number | null }[];
  metrika_phrases: { phrase: string; visits: number }[];
  commercial_block: { audience: string; tasks: string };
  problems: string[];
  warnings: string[];
  attempts: number;
  model: string;
  markdown: string;
}

const STATUS_TITLES: Record<Draft['status'], string> = {
  ready: 'Черновик готов, проверки пройдены',
  needs_review: 'Черновик требует проверки',
  needs_data: 'Недостаточно данных',
  error: 'Черновик не создан',
};

@Component({
  selector: 'app-root',
  imports: [FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  private readonly http = inject(HttpClient);

  readonly providers = signal<Provider[]>([]);
  readonly examples = signal<Example[]>([]);
  readonly provider = signal('');
  readonly model = signal('');
  readonly product = signal('');
  readonly busy = signal(false);
  readonly failure = signal('');
  readonly draft = signal<Draft | null>(null);
  readonly copied = signal('');

  readonly models = computed(() => this.providers().find((item) => item.provider === this.provider())?.models ?? []);
  readonly statusTitle = computed(() => {
    const draft = this.draft();
    return draft ? STATUS_TITLES[draft.status] : '';
  });

  constructor() {
    this.http.get<{ providers: Provider[] }>('/api/models').subscribe({
      next: (data) => {
        this.providers.set(data.providers);
        if (data.providers.length === 1) {
          this.chooseProvider(data.providers[0].provider);
        }
      },
      error: () => this.failure.set('Нет связи с сервером: список моделей не получен.'),
    });
    this.http.get<{ examples: Example[] }>('/api/examples').subscribe({
      next: (data) => {
        this.examples.set(data.examples);
        this.product.set(data.examples[0]?.product ?? '');
      },
    });
  }

  chooseProvider(provider: string): void {
    this.provider.set(provider);
    this.model.set('');
  }

  submit(): void {
    this.busy.set(true);
    this.failure.set('');
    this.draft.set(null);
    const body = { product: this.product(), provider: this.provider(), model: this.model() };
    this.http.post<Draft>('/api/draft', body).subscribe({
      next: (draft) => {
        this.draft.set(draft);
        this.busy.set(false);
      },
      error: (error: HttpErrorResponse) => {
        this.failure.set(error.error?.detail ?? 'Нет связи с сервером: проверьте, что он запущен.');
        this.busy.set(false);
      },
    });
  }

  copy(label: string, text: string): void {
    navigator.clipboard.writeText(text).then(
      () => this.copied.set(label),
      () => this.copied.set(''),
    );
  }

  asJson(draft: Draft): string {
    const { markdown, ...card } = draft;
    return JSON.stringify(card, null, 2);
  }

  queryLine(item: { query: string; frequency: number | null }): string {
    return item.frequency === null ? 'частотность не проверена' : `${item.frequency} показов в месяц`;
  }

  /** Положение стрелки на шкале длины: процент от всей шкалы. */
  gauge(length: number, max: number): number {
    return Math.min(100, (length / max) * 100);
  }
}
