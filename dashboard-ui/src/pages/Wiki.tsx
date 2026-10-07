import { useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { BookOpen, ChevronRight, FolderOpen, Lightbulb, Search } from 'lucide-react';
import { APP_VERSION } from '../lib/version';
import { wikiArticles, wikiFolders } from '../lib/wiki';

export function Wiki() {
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState('');
  const selected = wikiArticles.find(article => article.id === params.get('article'));
  const folder = wikiFolders.includes(params.get('folder') || '') ? params.get('folder') : null;
  const needle = query.trim().toLocaleLowerCase('ru');
  const articles = wikiArticles.filter(article => (!folder || article.folder === folder) &&
    [article.title, article.folder, article.audience, article.summary, article.example, article.note || '', ...article.steps].join(' ').toLocaleLowerCase('ru').includes(needle));
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="tf-panel-flat relative overflow-hidden p-6 sm:p-8">
        <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-[var(--color-accent)]"><BookOpen size={19} />СПРАВОЧНИК TASKFLOW <span className="tf-chip">{APP_VERSION}</span></div>
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Освойтесь. Настройте. Работайте.</h1>
        <p className="mt-3 max-w-2xl text-[var(--color-text-secondary)]">Короткие инструкции, понятные правила и примеры. Для каждого, кто работает в приложении.</p>
        <label className="relative mt-6 block max-w-xl">
          <span className="sr-only">Поиск по Вики</span>
          <Search size={18} className="absolute left-3 top-3 text-[var(--color-muted)]" />
          <input className="tf-input pl-10" value={query} onChange={event => { setQuery(event.target.value); if (selected) setParams({}); }} placeholder="Как создать пользователя? Что такое роль?" />
        </label>
      </header>
      <div className="grid items-start gap-6 lg:grid-cols-[230px_minmax(0,1fr)]">
        <nav aria-label="Разделы Вики" className="tf-panel-flat space-y-1 p-3 lg:sticky lg:top-4">
          <button onClick={() => setParams({})} className={`tf-button w-full justify-start ${!folder && !selected ? 'tf-button-primary' : ''}`}><BookOpen size={16} />Все статьи <span className="ml-auto">{wikiArticles.length}</span></button>
          {wikiFolders.map(name => <button key={name} onClick={() => setParams({ folder: name })} className={`tf-button h-auto w-full justify-start py-3 text-left ${folder === name || selected?.folder === name ? 'bg-[var(--color-overlay-strong)]' : ''}`}><FolderOpen size={16} className="shrink-0" /><span>{name}</span></button>)}
          <p className="px-3 pt-4 text-xs leading-5 text-[var(--color-muted)]">Справка доступна всем вошедшим пользователям, даже без окружения. Ссылкой на статью можно поделиться с коллегой.</p>
        </nav>
        <main className="min-w-0">
          {selected ? <article className="tf-panel-flat p-5 sm:p-8">
            <div className="mb-5 flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-secondary)]"><Link to="/wiki">Вики</Link><ChevronRight size={13} /><button onClick={() => setParams({ folder: selected.folder })}>{selected.folder}</button></div>
            <span className="tf-chip">{selected.audience}</span>
            <h2 className="mt-4 text-2xl font-bold sm:text-3xl">{selected.title}</h2>
            <p className="mt-3 leading-7 text-[var(--color-text-secondary)]">{selected.summary}</p>
            <ol className="my-7 space-y-4">{selected.steps.map((step, i) => <li key={step} className="flex gap-3"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[var(--color-overlay-strong)] text-xs font-bold">{i + 1}</span><p className="pt-0.5 text-sm leading-6">{step}</p></li>)}</ol>
            <aside className="rounded-2xl border border-[var(--color-accent)]/30 bg-[var(--color-overlay)] p-5"><h3 className="mb-2 flex items-center gap-2 text-sm font-bold"><Lightbulb size={17} />На примере</h3><p className="text-sm leading-6">{selected.example}</p></aside>
            {selected.note && <p className="mt-5 border-l-2 border-[var(--color-border-strong)] pl-4 text-sm leading-6 text-[var(--color-text-secondary)]">{selected.note}</p>}
            <div className="mt-8 border-t border-[var(--color-border)] pt-5"><h3 className="mb-3 text-sm font-bold">Рядом по теме</h3><div className="flex flex-wrap gap-2">{wikiArticles.filter(a => a.folder === selected.folder && a.id !== selected.id).map(a => <Link className="tf-button h-auto py-2 text-left text-xs" key={a.id} to={`/wiki?article=${a.id}`}>{a.title}<ChevronRight size={14} /></Link>)}</div></div>
          </article> : <>
            <div className="mb-4 flex items-center justify-between"><h2 className="text-xl font-bold">{needle ? 'Результаты поиска' : folder || 'Все инструкции'}</h2><span className="tf-chip">{articles.length}</span></div>
            <div className="grid gap-4 sm:grid-cols-2">{articles.map(article => <Link key={article.id} to={`/wiki?article=${article.id}`} className="tf-panel-flat group flex flex-col p-5 transition hover:border-[var(--color-accent)] focus-visible:outline-2 focus-visible:outline-[var(--color-accent)]"><span className="text-xs font-semibold text-[var(--color-muted)]">{article.folder}</span><h3 className="mt-3 text-lg font-bold">{article.title}</h3><p className="mb-5 mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{article.summary}</p><span className="mt-auto flex items-center justify-between text-xs font-semibold text-[var(--color-accent)]">Читать инструкцию<ChevronRight size={16} /></span></Link>)}</div>
            {!articles.length && <div className="tf-panel-flat p-8 text-center"><Search className="mx-auto mb-3" /><p>Ничего не найдено. Попробуйте «права», «пользователь» или «окружение».</p><button className="tf-button mt-4" onClick={() => { setQuery(''); setParams({}); }}>Показать все статьи</button></div>}
          </>}
        </main>
      </div>
    </div>
  );
}
