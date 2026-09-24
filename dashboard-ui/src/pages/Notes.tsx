import { useEffect, useMemo, useRef, useState } from 'react';
import { Copy, Download, Eye, FolderPlus, Globe, HardDrive, Lock, Pencil, Plus, RotateCcw, Search, Server, StickyNote, Tag, Trash2, X } from 'lucide-react';
import { api, type Note, type NoteFolder } from '../api/client';
import { SearchSelect } from '../components/SearchSelect';
import { Select } from '../components/Select';
import { RichTextEditor } from '../components/RichTextEditor';
import { formatFullDate, cn } from '../lib/taskflow';
import {
  createLocalFolder,
  createLocalNote,
  deleteLocalFolder,
  duplicateLocalNote,
  listLocalFolders,
  listLocalNotes,
  purgeLocalNote,
  restoreLocalNote,
  softDeleteLocalNote,
  updateLocalNote,
  type LocalFolder,
  type LocalNote,
} from '../lib/localNotes';

const APPLE_FONT = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', Inter, 'Segoe UI', sans-serif";
const ACCENT = 'var(--color-accent)';
const ON_ACCENT = 'var(--color-on-accent)';

const NOTE_FORMATS: Record<string, string> = {
  markdown: 'Markdown',
  text: 'Текст',
  code: 'Код',
  html: 'HTML',
};

type Tab = 'mine' | 'shared' | 'trash';

type ViewNote = {
  uid: string;
  origin: 'server' | 'local';
  id: number | string;
  title: string;
  content: string;
  format: string;
  tags: string[];
  folderId: string;
  folderName: string | null;
  is_public: boolean;
  username: string | null;
  is_owner: boolean;
  updated_at: string;
  deleted_at: string | null;
};

function toViewServer(n: Note): ViewNote {
  return {
    uid: `s-${n.id}`,
    origin: 'server',
    id: n.id,
    title: n.title,
    content: n.content,
    format: n.format,
    tags: n.tags,
    folderId: n.folder_id != null ? String(n.folder_id) : '',
    folderName: n.folder_name,
    is_public: n.is_public,
    username: n.username,
    is_owner: n.is_owner,
    updated_at: n.updated_at || n.created_at || '',
    deleted_at: n.deleted_at,
  };
}

function toViewLocal(n: LocalNote, folderName: (id: string) => string): ViewNote {
  return {
    uid: `l-${n.id}`,
    origin: 'local',
    id: n.id,
    title: n.title,
    content: n.content,
    format: n.format,
    tags: n.tags,
    folderId: n.folderId,
    folderName: n.folderId ? folderName(n.folderId) : null,
    is_public: false,
    username: null,
    is_owner: true,
    updated_at: n.updated_at,
    deleted_at: n.deleted_at,
  };
}

export function Notes() {
  const [tab, setTab] = useState<Tab>('mine');
  const [notes, setNotes] = useState<ViewNote[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [serverFolders, setServerFolders] = useState<NoteFolder[]>([]);
  const [localFolders, setLocalFolders] = useState<LocalFolder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [folder, setFolder] = useState('');
  const [tag, setTag] = useState('');
  const [format, setFormat] = useState('');

  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<ViewNote | null>(null);
  const [newFolderName, setNewFolderName] = useState('');
  const [folderEditorOpen, setFolderEditorOpen] = useState(false);

  const trash = tab === 'trash';

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (search) params.set('q', search);
      if (format) params.set('fmt', format);
      if (tag) params.set('tag', tag);
      const query = params.toString();

      if (tab === 'shared') {
        const withFolder = new URLSearchParams(query);
        if (folder) withFolder.set('folder_id', folder);
        const [list, folderList] = await Promise.all([
          api.getNotes(withFolder.toString()),
          api.getNoteFolders().catch(() => [] as NoteFolder[]),
        ]);
        setNotes(list.notes.filter(n => n.is_public).map(toViewServer));
        setTags(list.tags);
        setServerFolders(folderList);
        setLocalFolders(await listLocalFolders().catch(() => []));
      } else {
        // «Мои» и «Корзина»: локальные + собственные серверные
        const [local, server, localFolderList, serverFolderList] = await Promise.all([
          listLocalNotes({ q: search, folderId: folder || undefined, tag: tag || undefined, format: format || undefined, trash }),
          api.getNotes(`${query}${query ? '&' : ''}${trash ? 'archived=true' : 'scope=mine'}`),
          listLocalFolders().catch(() => [] as LocalFolder[]),
          api.getNoteFolders().catch(() => [] as NoteFolder[]),
        ]);
        const localMap = new Map(localFolderList.map(f => [f.id, f.name]));
        const localView = local.notes.map(n => toViewLocal(n, id => localMap.get(id) || '—'));
        let serverView = server.notes.map(toViewServer);
        if (tab === 'mine' && folder) {
          // серверные показываем только из выбранной локальной папки? нет — папки разные,
          // поэтому при фильтре по папке серверные скрываем, чтобы не врать
          serverView = [];
        }
        const merged = [...localView, ...serverView].sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
        setNotes(merged);
        setTags(Array.from(new Set([...local.tags, ...server.tags])).sort());
        setServerFolders(serverFolderList);
        setLocalFolders(localFolderList);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить заметки.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, search, folder, tag, format]);

  const switchTab = (next: Tab) => {
    setTab(next);
    setFolder('');
    setTag('');
  };

  const openCreate = () => {
    setEditing(null);
    setEditorOpen(true);
  };

  const openEdit = (note: ViewNote) => {
    setEditing(note);
    setEditorOpen(true);
  };

  const saveNote = async (data: Record<string, any>) => {
    setSaving(true);
    setError('');
    try {
      if (editing?.origin === 'server' && typeof editing.id === 'number') {
        await api.updateNote(editing.id, {
          title: data.title,
          content: data.content,
          format: data.format,
          tags: data.tags,
          is_public: data.is_public,
          folder_id: data.folder_id ? Number(data.folder_id) : null,
        });
      } else if (editing?.origin === 'local') {
        if (data.is_public) {
          // переезд локальной заметки на сервер
          await api.createNote({ title: data.title, content: data.content, format: data.format, tags: data.tags, is_public: true });
          await purgeLocalNote(String(editing.id));
        } else {
          await updateLocalNote(String(editing.id), {
            title: data.title,
            content: data.content,
            format: data.format,
            tags: data.tags,
            folderId: data.folder_id || '',
          });
        }
      } else if (data.is_public) {
        await api.createNote({
          title: data.title,
          content: data.content,
          format: data.format,
          tags: data.tags,
          is_public: true,
          folder_id: data.folder_id ? Number(data.folder_id) : null,
        });
      } else {
        await createLocalNote({
          title: data.title,
          content: data.content,
          format: data.format,
          tags: data.tags,
          folderId: data.folder_id || '',
        });
      }
      setEditorOpen(false);
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить заметку.');
    } finally {
      setSaving(false);
    }
  };

  const moveToTrash = async (note: ViewNote) => {
    if (!confirm(`Удалить заметку «${note.title}» в корзину?`)) return;
    try {
      if (note.origin === 'local') await softDeleteLocalNote(String(note.id));
      else if (typeof note.id === 'number') await api.deleteNote(note.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось удалить заметку.');
    }
  };

  const restore = async (note: ViewNote) => {
    try {
      if (note.origin === 'local') await restoreLocalNote(String(note.id));
      else if (typeof note.id === 'number') await api.restoreNote(note.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось восстановить заметку.');
    }
  };

  const purge = async (note: ViewNote) => {
    if (!confirm(`Удалить заметку «${note.title}» навсегда? Это действие необратимо.`)) return;
    try {
      if (note.origin === 'local') await purgeLocalNote(String(note.id));
      else if (typeof note.id === 'number') await api.deleteNote(note.id, true);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось удалить заметку.');
    }
  };

  const duplicate = async (note: ViewNote) => {
    try {
      if (note.origin === 'local') await duplicateLocalNote(String(note.id));
      else if (typeof note.id === 'number') await api.duplicateNote(note.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось дублировать заметку.');
    }
  };

  const downloadToPc = async (note: ViewNote) => {
    if (note.origin !== 'server' || typeof note.id !== 'number') return;
    if (!confirm('Скачать заметку на этот ПК и удалить её с сервера?')) return;
    try {
      await createLocalNote({ title: note.title, content: note.content, format: note.format, tags: note.tags, folderId: '' });
      await api.deleteNote(note.id, true);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось перенести заметку.');
    }
  };

  const createFolder = async () => {
    const name = newFolderName.trim();
    if (!name) return;
    try {
      if (tab === 'shared') await api.createNoteFolder({ name });
      else await createLocalFolder(name);
      setNewFolderName('');
      setFolderEditorOpen(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать папку.');
    }
  };

  const removeFolder = async (id: string, name: string) => {
    if (!confirm(`Удалить папку «${name}»? Заметки останутся без папки.`)) return;
    try {
      if (tab === 'shared') await api.deleteNoteFolder(Number(id));
      else await deleteLocalFolder(id);
      if (folder === id) setFolder('');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось удалить папку.');
    }
  };

  const folders = tab === 'shared' ? serverFolders.map(f => ({ id: String(f.id), name: f.name })) : localFolders;
  const folderName = useMemo(() => {
    const map = new Map(folders.map(f => [f.id, f.name]));
    return (id: string) => (id ? map.get(id) || '—' : 'Без папки');
  }, [folders]);

  const hasFilters = search || folder || tag || format;

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-2 pb-16 sm:px-6" style={{ fontFamily: APPLE_FONT }}>
      <header className="relative overflow-visible pt-4 sm:pt-8">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-24 left-1/2 h-72 w-[42rem] -translate-x-1/2 rounded-full"
          style={{ background: 'radial-gradient(closest-side, rgba(120,100,70,.14), transparent)' }}
        />
        <div className="relative flex flex-wrap items-end gap-6">
          <div className="min-w-0">
            <h2 className="text-4xl font-semibold tracking-tight text-[var(--color-text)] sm:text-5xl">Заметки</h2>
            <p className="mt-3 max-w-xl text-[17px] leading-relaxed text-[var(--color-text-secondary)]">
              Общие живут на сервере. Личные — только на этом ПК.
            </p>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-3">
            {!trash && (
              <button
                type="button"
                onClick={() => setFolderEditorOpen(prev => !prev)}
                className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-2.5 text-[15px] font-medium text-[var(--color-text)] transition hover:border-[var(--color-border-strong)] active:scale-[.98]"
                style={{ boxShadow: 'var(--shadow-soft)' }}
              >
                <FolderPlus size={17} /> Папки
              </button>
            )}
            {!trash && (
              <button
                type="button"
                onClick={openCreate}
                className="inline-flex items-center gap-2 rounded-full px-6 py-2.5 text-[15px] font-semibold transition hover:brightness-125 active:scale-[.98]"
                style={{ background: ACCENT, color: ON_ACCENT, boxShadow: 'var(--shadow-accent)' }}
              >
                <Plus size={17} strokeWidth={2.5} /> Новая заметка
              </button>
            )}
          </div>
        </div>
        <div className="relative mt-6 flex flex-wrap gap-2.5">
          <Pill active={tab === 'mine'} onClick={() => switchTab('mine')}><HardDrive size={15} /> Мои</Pill>
          <Pill active={tab === 'shared'} onClick={() => switchTab('shared')}><Server size={15} /> Общие</Pill>
          <Pill active={tab === 'trash'} onClick={() => switchTab('trash')}><Trash2 size={15} /> Корзина</Pill>
        </div>
      </header>

      <div className="relative mx-auto max-w-2xl">
        <Search size={18} className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-[var(--color-muted)]" />
        <input
          value={searchInput}
          onChange={event => setSearchInput(event.target.value)}
          onKeyDown={event => { if (event.key === 'Enter') setSearch(searchInput.trim()); }}
          placeholder="Поиск по названию, тексту, тегам"
          className="h-[52px] w-full rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] pl-[52px] pr-24 text-[16px] text-[var(--color-text)] placeholder-[var(--color-muted)] outline-none transition focus:border-[var(--color-focus-border)] focus:ring-4 focus:ring-[var(--color-ring)]"
          style={{ boxShadow: 'var(--shadow-soft)' }}
        />
        <button
          type="button"
          onClick={() => setSearch(searchInput.trim())}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full px-5 py-2 text-[15px] font-semibold transition hover:brightness-125 active:scale-[.98]"
          style={{ background: ACCENT, color: ON_ACCENT }}
        >
          Найти
        </button>
      </div>

      {!trash && (
        <section className="space-y-4">
          <div className="flex flex-wrap items-center gap-2.5">
            <Pill active={folder === ''} onClick={() => setFolder('')}>Все</Pill>
            <Pill active={folder === 'root'} onClick={() => setFolder('root')}>Без папки</Pill>
            {folders.map(f => (
              <Pill key={f.id} active={folder === f.id} onClick={() => setFolder(folder === f.id ? '' : f.id)}>
                {f.name}
              </Pill>
            ))}
          </div>

          {folderEditorOpen && (
            <div className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6" style={{ boxShadow: 'var(--shadow-soft)' }}>
              <div className="text-sm font-semibold text-[var(--color-text)]">
                {tab === 'shared' ? 'Папки на сервере' : 'Папки на этом ПК'}
              </div>
              <div className="mt-3 flex flex-wrap gap-3">
                <input
                  value={newFolderName}
                  onChange={event => setNewFolderName(event.target.value)}
                  onKeyDown={event => { if (event.key === 'Enter') void createFolder(); }}
                  placeholder="Название новой папки"
                  maxLength={200}
                  className="tf-input min-w-[220px] flex-1 rounded-full"
                />
                <button
                  type="button"
                  onClick={createFolder}
                  className="rounded-full px-6 py-2.5 text-[15px] font-semibold transition hover:brightness-125 active:scale-[.98]"
                  style={{ background: ACCENT, color: ON_ACCENT }}
                >
                  Создать
                </button>
              </div>
              {folders.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {folders.map(f => (
                    <span key={f.id} className="inline-flex items-center gap-2 rounded-full bg-[var(--color-overlay)] py-1.5 pl-4 pr-2 text-[14px] text-[var(--color-text)]">
                      {f.name}
                      <button
                        type="button"
                        onClick={() => removeFolder(f.id, f.name)}
                        className="grid h-6 w-6 place-items-center rounded-full text-[var(--color-muted)] transition hover:bg-[var(--color-overlay-strong)] hover:text-[var(--color-text)]"
                        aria-label={`Удалить папку ${f.name}`}
                      >
                        <X size={13} />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>
      )}

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 text-[14px]">
        <Select size="pill" value={format} onChange={setFormat} label="Формат" options={[{ value: '', label: 'Любой' }, ...Object.entries(NOTE_FORMATS).map(([key, label]) => ({ value: key, label }))]} />
        {tags.length > 0 && (
          <Select size="pill" value={tag} onChange={setTag} label="Тег" options={[{ value: '', label: 'Все теги' }, ...tags.map(t => ({ value: t, label: t }))]} searchPlaceholder="Найти тег..." />
        )}
        {hasFilters && (
          <button type="button" onClick={() => { setSearchInput(''); setSearch(''); setFolder(''); setTag(''); setFormat(''); }} className="text-[14px] font-semibold text-[var(--color-text)] underline decoration-[var(--color-border-strong)] underline-offset-4">
            Сбросить всё
          </button>
        )}
      </div>

      {error && (
        <div className="rounded-[20px] border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/[.07] px-6 py-4 text-[15px] font-medium text-[var(--color-danger)]">
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid h-56 place-items-center">
          <div className="flex items-center gap-3 text-[16px] text-[var(--color-text-secondary)]">
            <span className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--color-border-strong)] border-t-[var(--color-text)]" />
            Загрузка заметок...
          </div>
        </div>
      ) : notes.length === 0 ? (
        <div className="grid place-items-center rounded-[28px] border border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-20 text-center" style={{ boxShadow: 'var(--shadow-soft)' }}>
          <div className="grid h-20 w-20 place-items-center rounded-[24px] bg-[var(--color-overlay)]">
            <StickyNote size={34} className="text-[var(--color-muted)]" strokeWidth={1.5} />
          </div>
          <p className="mt-6 text-[22px] font-semibold tracking-tight text-[var(--color-text)]">
            {trash ? 'Корзина пуста' : 'Пока пусто'}
          </p>
          <p className="mt-2 max-w-sm text-[15px] leading-relaxed text-[var(--color-text-secondary)]">
            {trash
              ? 'Удалённые заметки появятся здесь. Их можно восстановить или удалить навсегда.'
              : tab === 'shared'
                ? 'Отметьте заметку как общую — и она появится здесь для всех.'
                : 'Создайте первую заметку — идея, черновик или сниппет. Это займёт пару секунд.'}
          </p>
          {!trash && (
            <button
              type="button"
              onClick={openCreate}
              className="mt-7 inline-flex items-center gap-2 rounded-full px-7 py-3 text-[16px] font-semibold transition hover:brightness-125 active:scale-[.98]"
              style={{ background: ACCENT, color: ON_ACCENT, boxShadow: 'var(--shadow-accent)' }}
            >
              <Plus size={17} strokeWidth={2.5} /> Создать заметку
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          {notes.map((note, index) => (
            <article
              key={note.uid}
              onClick={() => !trash && openEdit(note)}
              className={cn(
                'anim-rise group rounded-[24px] border border-[var(--color-border)] bg-[var(--color-surface)] p-6 transition duration-300 sm:p-7',
                !trash && 'cursor-pointer hover:-translate-y-1',
              )}
              style={{ boxShadow: 'var(--shadow-soft)', animationDelay: `${Math.min(index * 45, 360)}ms` }}
            >
              <div className="flex items-start gap-4">
                <div className="min-w-0 flex-1">
                  <h3 className="truncate text-[19px] font-semibold tracking-tight text-[var(--color-text)]">{note.title}</h3>
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-[var(--color-muted)]">
                    <OriginBadge note={note} />
                    <span>{NOTE_FORMATS[note.format] || note.format}</span>
                    <span>{note.folderId ? folderName(note.folderId) : 'Без папки'}</span>
                    {note.username && <span>· {note.username}</span>}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5 opacity-0 transition group-hover:opacity-100" onClick={event => event.stopPropagation()}>
                  {!trash && (
                    <CircleButton onClick={() => openEdit(note)} title={note.is_owner ? 'Редактировать' : 'Просмотр'}>
                      {note.is_owner ? <Pencil size={15} /> : <Eye size={15} />}
                    </CircleButton>
                  )}
                  {!trash && note.is_owner && (
                    <CircleButton onClick={() => duplicate(note)} title="Дублировать">
                      <Copy size={15} />
                    </CircleButton>
                  )}
                  {!trash && note.origin === 'server' && note.is_owner && typeof note.id === 'number' && (
                    <CircleButton onClick={() => downloadToPc(note)} title="Скачать на этот ПК">
                      <Download size={15} />
                    </CircleButton>
                  )}
                  {!trash && note.is_owner && (
                    <CircleButton danger onClick={() => moveToTrash(note)} title="В корзину">
                      <Trash2 size={15} />
                    </CircleButton>
                  )}
                  {trash && (
                    <CircleButton onClick={() => restore(note)} title="Восстановить">
                      <RotateCcw size={15} />
                    </CircleButton>
                  )}
                  {trash && (
                    <CircleButton danger onClick={() => purge(note)} title="Удалить навсегда">
                      <Trash2 size={15} />
                    </CircleButton>
                  )}
                </div>
              </div>
              {note.tags.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {note.tags.map(t => (
                    <button
                      key={t}
                      type="button"
                      onClick={event => { event.stopPropagation(); setTag(t); }}
                      className="inline-flex items-center gap-1 rounded-full bg-[var(--color-overlay)] px-3 py-1 text-[12.5px] font-medium text-[var(--color-text-secondary)] transition hover:bg-[var(--color-overlay-strong)] hover:text-[var(--color-text)]"
                    >
                      <Tag size={11} />{t}
                    </button>
                  ))}
                </div>
              )}
              <p className="mt-4 line-clamp-3 text-[15px] leading-relaxed text-[var(--color-text-secondary)]">
                {plainText(note.content).slice(0, 280) || 'Пустая заметка'}
              </p>
              <p className="mt-5 text-[12.5px] text-[var(--color-muted)]">
                Обновлена: {formatFullDate(note.updated_at)}
              </p>
            </article>
          ))}
        </div>
      )}

      {editorOpen && (
        <NoteModal
          note={editing}
          serverFolders={serverFolders}
          localFolders={localFolders}
          saving={saving}
          onClose={() => { setEditorOpen(false); setEditing(null); }}
          onSave={saveNote}
        />
      )}
    </div>
  );
}

function OriginBadge({ note }: { note: ViewNote }) {
  if (note.origin === 'local') {
    return (
      <span className="inline-flex items-center gap-1.5 font-medium text-[var(--color-text-secondary)]">
        <HardDrive size={13} /> На этом ПК
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 font-medium text-[var(--color-text-secondary)]">
      {note.is_public ? <Globe size={13} /> : <Lock size={13} />}
      {note.is_public ? 'Общая · сервер' : 'Личная · сервер'}
    </span>
  );
}

function Pill({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-2 rounded-full px-5 py-2 text-[14.5px] font-medium transition active:scale-[.97]',
        active ? '' : 'bg-[var(--color-overlay)] text-[var(--color-text-secondary)] hover:bg-[var(--color-overlay-strong)] hover:text-[var(--color-text)]',
      )}
      style={active ? { background: ACCENT, color: ON_ACCENT, boxShadow: 'var(--shadow-accent)' } : undefined}
    >
      {children}
    </button>
  );
}

function CircleButton({ onClick, title, danger, children }: {
  onClick: () => void;
  title: string;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={title}
      className={cn(
        'grid h-9 w-9 place-items-center rounded-full bg-[var(--color-overlay)] text-[var(--color-text-secondary)] transition hover:bg-[var(--color-overlay-strong)] hover:text-[var(--color-text)] active:scale-95',
        danger && 'hover:bg-[var(--color-danger)]/15 hover:text-[var(--color-danger)]',
      )}
    >
      {children}
    </button>
  );
}

function NoteModal({ note, serverFolders, localFolders, saving, onClose, onSave }: {
  note: ViewNote | null;
  serverFolders: NoteFolder[];
  localFolders: LocalFolder[];
  saving: boolean;
  onClose: () => void;
  onSave: (data: Record<string, any>) => Promise<void>;
}) {
  const [title, setTitle] = useState(note?.title || '');
  const [content, setContent] = useState(note?.content || '');
  const [format, setFormat] = useState(note?.format || 'markdown');
  const [tags, setTags] = useState((note?.tags || []).join(', '));
  const [isPublic, setIsPublic] = useState(note ? note.is_public : false);
  const [folderId, setFolderId] = useState(note?.folderId || '');
  const [error, setError] = useState('');

  const origin: 'server' | 'local' = note?.origin || (isPublic ? 'server' : 'local');
  const folderOptions = origin === 'server'
    ? serverFolders.map(f => ({ id: String(f.id), name: f.name }))
    : localFolders.map(f => ({ id: f.id, name: f.name }));

  // при смене типа (личная/общая) папка другого хранилища не подходит — сбрасываем
  const prevOrigin = useRef(origin);
  useEffect(() => {
    if (prevOrigin.current !== origin) {
      prevOrigin.current = origin;
      setFolderId('');
    }
  }, [origin]);

  const initialSnapshot = useMemo(() => ({
    title: note?.title || '',
    content: note?.content || '',
    format: note?.format || 'markdown',
    tags: (note?.tags || []).join(', '),
    isPublic: note ? note.is_public : false,
    folderId: note?.folderId || '',
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), []);

  const isDirty =
    title !== initialSnapshot.title ||
    content !== initialSnapshot.content ||
    format !== initialSnapshot.format ||
    tags !== initialSnapshot.tags ||
    isPublic !== initialSnapshot.isPublic ||
    folderId !== initialSnapshot.folderId;

  const requestClose = () => {
    if (!isDirty || confirm('Есть несохранённые изменения. Закрыть без сохранения?')) onClose();
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    if (!title.trim()) {
      setError('Заголовок не может быть пустым.');
      return;
    }
    try {
      await onSave({
        title: title.trim(),
        content,
        format,
        tags: tags.split(',').map(t => t.trim()).filter(Boolean),
        is_public: isPublic,
        folder_id: folderId,
      });
    } catch {
      setError('Не удалось сохранить заметку.');
    }
  };

  return (
    <div className="anim-modal fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/45 p-3 backdrop-blur-sm sm:p-6" onClick={requestClose} style={{ fontFamily: APPLE_FONT }}>
      <form
        onSubmit={submit}
        className="tf-modal-shell flex max-h-[92dvh] w-full max-w-4xl flex-col overflow-hidden"
        onClick={event => event.stopPropagation()}
      >
        <div className="flex shrink-0 items-center gap-4 px-7 pb-5 pt-7 sm:px-9">
          <h2 className="text-[24px] font-semibold tracking-tight text-[var(--color-text)]">
            {note ? 'Заметка' : 'Новая заметка'}
          </h2>
          {note && (
            <span className="rounded-full bg-[var(--color-overlay)] px-3 py-1 text-[12.5px] font-medium text-[var(--color-text-secondary)]">
              {note.origin === 'local' ? 'На этом ПК' : 'На сервере'}
            </span>
          )}
          <button
            type="button"
            onClick={requestClose}
            aria-label="Закрыть"
            className="ml-auto grid h-9 w-9 place-items-center rounded-full bg-[var(--color-overlay)] text-[var(--color-text-secondary)] transition hover:bg-[var(--color-overlay-strong)] hover:text-[var(--color-text)] active:scale-95"
          >
            <X size={17} />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-7 pb-2 sm:px-9">
          <input
            value={title}
            onChange={event => setTitle(event.target.value)}
            placeholder="Заголовок"
            required
            autoFocus
            maxLength={200}
            className="w-full bg-transparent text-[28px] font-semibold tracking-tight text-[var(--color-text)] placeholder-[var(--color-muted)] outline-none"
          />

          <div className="flex flex-wrap items-center gap-2.5">
            {Object.entries(NOTE_FORMATS).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setFormat(key)}
                className={cn(
                  'rounded-full px-4 py-1.5 text-[13.5px] font-medium transition active:scale-[.97]',
                  format === key ? '' : 'bg-[var(--color-overlay)] text-[var(--color-text-secondary)] hover:bg-[var(--color-overlay-strong)] hover:text-[var(--color-text)]',
                )}
                style={format === key ? { background: ACCENT, color: ON_ACCENT } : undefined}
              >
                {label}
              </button>
            ))}
            <span className="mx-1 h-5 w-px bg-[var(--color-border-strong)]" />
            <button
              type="button"
              onClick={() => setIsPublic(prev => !prev)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-[13.5px] font-medium transition active:scale-[.97]',
                isPublic ? '' : 'bg-[var(--color-overlay)] text-[var(--color-text-secondary)] hover:bg-[var(--color-overlay-strong)] hover:text-[var(--color-text)]',
              )}
              style={isPublic ? { background: '#5f8f6a', color: '#fff' } : undefined}
              title={isPublic ? 'Хранится на сервере, видна всем' : 'Хранится только на этом ПК'}
            >
              {isPublic ? <Globe size={13} /> : <Lock size={13} />}
              {isPublic ? 'Общая' : 'Личная'}
            </button>
          </div>
          <p className="-mt-3 text-[13px] text-[var(--color-muted)]">
            {isPublic
              ? 'Общая заметка хранится на сервере.'
              : origin === 'server'
                ? 'Серверная заметка. Кнопка «Скачать на ПК» в списке перенесёт её только на этот компьютер.'
                : 'Личная заметка хранится только на этом ПК и никуда не отправляется.'}
          </p>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-[13px] font-medium text-[var(--color-text-secondary)]">
                Папка {origin === 'server' ? '(на сервере)' : '(на этом ПК)'}
              </span>
              <SearchSelect
                value={folderId}
                options={folderOptions.map(f => ({ value: f.id, label: f.name }))}
                onChange={setFolderId}
                emptyLabel="Без папки"
                placeholder="Выберите папку"
                searchPlaceholder="Найти папку..."
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-[13px] font-medium text-[var(--color-text-secondary)]">Теги через запятую</span>
              <input
                value={tags}
                onChange={event => setTags(event.target.value)}
                placeholder="идеи, seo, черновик"
                className="tf-input h-12 rounded-2xl text-[15px]"
              />
            </label>
          </div>

          <div className="overflow-hidden rounded-[20px] border border-[var(--color-border)] bg-[var(--color-input-bg)] p-1">
            <RichTextEditor value={content} onChange={setContent} minHeightClassName="min-h-64" placeholder="Начните писать..." />
          </div>

          {error && <div className="text-[14.5px] font-medium text-[var(--color-danger)]">{error}</div>}
        </div>

        <div className="flex shrink-0 items-center gap-3 px-7 py-5 sm:px-9">
          <button
            type="button"
            onClick={requestClose}
            className="tf-button rounded-full px-6"
          >
            Отмена
          </button>
          <button
            type="submit"
            disabled={saving}
            className="rounded-full px-8 py-2.5 text-[15px] font-semibold transition hover:brightness-125 active:scale-[.98] disabled:opacity-60"
            style={{ background: ACCENT, color: ON_ACCENT, boxShadow: 'var(--shadow-accent)' }}
          >
            {saving ? 'Сохранение...' : note ? 'Готово' : 'Создать'}
          </button>
        </div>
      </form>
    </div>
  );
}

function plainText(html: string): string {
  return (html || '').replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
}
