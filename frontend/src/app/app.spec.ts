import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { App } from './app';

const PROVIDERS = {
  providers: [
    { provider: 'claude-cli', kind: 'подписка', models: ['haiku', 'sonnet'] },
    { provider: 'demo', kind: 'без ключей', models: ['записанные ответы'] },
  ],
};
const EXAMPLES = { examples: [{ title: 'БУСТ3', product: '{"name":"БУСТ3"}' }] };
const READY = {
  status: 'ready',
  name: 'БУСТ3',
  seo_title: 'Заголовок',
  seo_description: 'я'.repeat(1000),
  key_specs: [{ name: 'Питание', value: 'данных нет' }],
  search_queries: ['запрос'],
  query_stats: [{ query: 'запрос', frequency: null }],
  metrika_phrases: [],
  commercial_block: { audience: 'Кому', tasks: 'Задачи' },
  problems: [],
  warnings: [],
  attempts: 1,
  model: 'demo/записанные ответы',
  markdown: '# БУСТ3',
};

describe('App', () => {
  let http: HttpTestingController;

  async function create() {
    const fixture = TestBed.createComponent(App);
    http.expectOne('/api/models').flush(PROVIDERS);
    http.expectOne('/api/examples').flush(EXAMPLES);
    await fixture.whenStable();
    return fixture;
  }

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [App],
      providers: [provideZonelessChangeDetection(), provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('lists scanned providers and the example products', async () => {
    const fixture = await create();
    const text = fixture.nativeElement.textContent;
    expect(text).toContain('claude-cli');
    expect(text).toContain('БУСТ3');
  });

  it('picks demo when nothing else is available', async () => {
    const fixture = TestBed.createComponent(App);
    http.expectOne('/api/models').flush({ providers: [PROVIDERS.providers[1]] });
    http.expectOne('/api/examples').flush(EXAMPLES);
    await fixture.whenStable();
    expect(fixture.componentInstance.provider()).toBe('demo');
  });

  it('shows models of the chosen provider', async () => {
    const fixture = await create();
    fixture.componentInstance.chooseProvider('claude-cli');
    await fixture.whenStable();
    expect(fixture.nativeElement.querySelector('#model').textContent).toContain('sonnet');
  });

  it('sends the product and the chosen model', async () => {
    const fixture = await create();
    fixture.componentInstance.product.set('{"name":"Х"}');
    fixture.componentInstance.chooseProvider('claude-cli');
    fixture.componentInstance.model.set('sonnet');
    fixture.componentInstance.submit();
    const request = http.expectOne('/api/draft');
    expect(request.request.body).toEqual({ product: '{"name":"Х"}', provider: 'claude-cli', model: 'sonnet' });
    request.flush(READY);
  });

  it('shows the draft with its length against the limit', async () => {
    const fixture = await create();
    fixture.componentInstance.submit();
    http.expectOne('/api/draft').flush(READY);
    await fixture.whenStable();
    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Заголовок');
    expect(text).toContain('данных нет');
    expect(text).toContain('1000 из 800–1200');
    expect(text).toContain('demo/записанные ответы');
  });

  it('lists what to fix when review is needed', async () => {
    const fixture = await create();
    fixture.componentInstance.submit();
    http.expectOne('/api/draft').flush({ ...READY, status: 'needs_review', problems: ['Нет во входных данных: 0,5'] });
    await fixture.whenStable();
    expect(fixture.nativeElement.textContent).toContain('Нет во входных данных: 0,5');
  });

  it('shows the message from the server on error', async () => {
    const fixture = await create();
    fixture.componentInstance.submit();
    http.expectOne('/api/draft').flush({ detail: 'Некорректный JSON' }, { status: 400, statusText: 'Bad Request' });
    await fixture.whenStable();
    expect(fixture.nativeElement.textContent).toContain('Некорректный JSON');
  });

  it('does not call a server error a lost connection', async () => {
    const fixture = await create();
    fixture.componentInstance.submit();
    http.expectOne('/api/draft').flush('<html>', { status: 500, statusText: 'Error' });
    await fixture.whenStable();
    expect(fixture.nativeElement.textContent).toContain('Сервер вернул ошибку 500');
  });

  it('explains when the server cannot be reached', async () => {
    const fixture = await create();
    fixture.componentInstance.submit();
    http.expectOne('/api/draft').error(new ProgressEvent('error'));
    await fixture.whenStable();
    expect(fixture.nativeElement.textContent).toContain('Нет связи с сервером');
  });
});
