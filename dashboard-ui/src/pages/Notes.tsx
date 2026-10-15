import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { getActiveWorkspaceId } from '../lib/workspace';
import { linkedNotes } from '../lib/noteLinks';
import { folderMatches, folderSelection } from '../lib/noteFolders';
import { sectionLabel } from '../lib/uiconfig';
import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowRightLeft, Copy, Eye, FolderPlus, Globe, HardDrive, Lock, Pencil, Plus, RotateCcw, Search, Server, StickyNote, Tag, Trash2, X } from 'lucide-react';
import { moveNote, runNoteBatch, type MovableNote, type NoteLocation } from '../lib/noteOperations';
import { api, type Note, type NoteFolder } from '../api/client';
import { SearchSelect } from '../components/SearchSelect';
import { Select } from '../components/Select';
import { RichTextEditor } from '../components/RichTextEditor';
import { TextEditor } from '../components/TextEditor';
import { convertNoteFormat } from '../lib/editorHtml';
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

const APPLE_FONT = 'inherit';
const ACCENT = 'var(--color-accent)';
const ON_ACCENT = 'var(--color-on-accent)';

const NOTE_FORMATS: Record<string, string> = {
  markdown: 'Markdown',
  text: 'Текст',
  code: 'Код',
  html: 'Документ',
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
  const location = useLocation(); const navigate = useNavigate(); const { user } = useAuth();
  const [localOnly, setLocalOnly] = useState(false);
  const [view, setView] = useState<'list' | 'cards'>('list');
  const [sort, setSort] = useState('updated');
  const noteAccessKey = JSON.stringify([user?.id, getActiveWorkspaceId(), user?.permissions, user?.features, user?.field_access]);
  const [tab, setTab] = useState<Tab>('mine');
  const [notes, setNotes] = useState<ViewNote[]>([]);
  const [inventory, setInventory] = useState<ViewNote[]>([]);
  const [inventoryVersion, setInventoryVersion] = useState(0);
  useEffect(() => {
    let active = true;
    Promise.all([listLocalNotes({}), api.getNotes('').catch(() => ({ notes: [] as Note[] }))]).then(([local, server]) => {
      if (active) setInventory([...local.notes.map(note => toViewLocal(note, () => '')), ...server.notes.filter(note => !note.deleted_at).map(toViewServer)]);
    }).catch(() => {});
    return () => { active = false; };
  }, [inventoryVersion, noteAccessKey]);
  const [tags, setTags] = useState<string[]>([]);
  const [serverFolders, setServerFolders] = useState<NoteFolder[]>([]);
  const [localFolders, setLocalFolders] = useState<LocalFolder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const operationLock = useRef(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [notice, setNotice] = useState('');
  const [confirmation, setConfirmation] = useState<{ title: string; message: string; run: () => Promise<void> } | null>(null);
  const [moving, setMoving] = useState<ViewNote[] | null>(null);
  const [destination, setDestination] = useState('local:root');
  const liveScope = useRef(noteAccessKey);
  useEffect(() => { liveScope.current = noteAccessKey; setSelected([]); setMoving(null); setConfirmation(null); }, [noteAccessKey]);

  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  useEffect(() => { const timer = setTimeout(() => setSearch(searchInput.trim()), 300); return () => clearTimeout(timer); }, [searchInput]);
  const [folder, setFolder] = useState('');
  const [tag, setTag] = useState('');
  const [format, setFormat] = useState('');

  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<ViewNote | null>(null);
  const [newFolderName, setNewFolderName] = useState('');
  const [newFolderOrigin, setNewFolderOrigin] = useState('local');
  const [folderEditorOpen, setFolderEditorOpen] = useState(false);
  const editorScope = useRef(noteAccessKey);

  useEffect(() => {
    const state = location.state as { assistantNoteDraft?: { title: string; content: string }; userId?: number; workspace?: string } | null;
    if (!state?.assistantNoteDraft || state.userId !== user?.id || state.workspace !== getActiveWorkspaceId()) return;
    const draft = state.assistantNoteDraft;
    if (typeof draft.title !== 'string' || typeof draft.content !== 'string') return;
    setTab('mine'); setLocalOnly(true);
    editorScope.current = noteAccessKey;
    setEditing({ uid: 'assistant-local-draft', origin: 'local', id: '', title: draft.title.slice(0, 200), content: draft.content.slice(0, 100000), format: 'markdown', tags: [], folderId: '', folderName: null, is_public: false, username: null, is_owner: true, updated_at: '', deleted_at: null });
    setEditorOpen(true); navigate(location.pathname, { replace: true, state: null });
  }, [location.state, user?.id, navigate, location.pathname, noteAccessKey]);
  const sortedNotes = useMemo(() => [...notes].sort((a, b) => sort === 'title' ? a.title.localeCompare(b.title, 'ru') : b.updated_at.localeCompare(a.updated_at)), [notes, sort]);
  const trash = tab === 'trash';
  useEffect(() => { setSelected([]); }, [tab, folder, search, tag, format]);

  const loadRevision = useRef(0);
  const load = async () => {
    const revision = ++loadRevision.current;
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
        const chosen = folderSelection(folder);
        if (chosen.id) withFolder.set('folder_id', chosen.id);
        const [folderList, localFolderList] = await Promise.all([
          api.getNoteFolders().catch(() => [] as NoteFolder[]),
          listLocalFolders().catch(() => [] as LocalFolder[]),
        ]);
        let sharedNotes: Note[] = [];
        let sharedTags: string[] = [];
        try {
          const list = await api.getNotes(withFolder.toString());
          sharedNotes = list.notes;
          sharedTags = list.tags;
        } catch (err) {
          // Ошибка сервера (например 403) не должна ронять всю страницу заметок.
          if (revision === loadRevision.current) setError(err instanceof Error ? err.message : 'Не удалось загрузить заметки с сервера.');
        }
        if (revision !== loadRevision.current) return;
        setNotes(sharedNotes.filter(n => n.is_public).map(toViewServer));
        setTags(sharedTags);
        setServerFolders(folderList);
        setLocalFolders(localFolderList);
      } else {
        // «Мои» и «Корзина»: локальные + собственные серверные
        const [local, localFolderList, serverFolderList] = await Promise.all([
          listLocalNotes({ q: search, tag: tag || undefined, format: format || undefined, trash }),
          listLocalFolders().catch(() => [] as LocalFolder[]),
          api.getNoteFolders().catch(() => [] as NoteFolder[]),
        ]);
        let serverNotes: Note[] = [];
        let serverTags: string[] = [];
        try {
          const res = await api.getNotes(`${query}${query ? '&' : ''}${trash ? 'archived=true' : 'scope=mine'}`);
          serverNotes = res.notes;
          serverTags = res.tags;
        } catch (err) {
          // Ошибка сервера не должна скрывать локальные заметки.
          if (revision === loadRevision.current) setError(err instanceof Error ? err.message : 'Не удалось загрузить заметки с сервера.');
        }
        const localMap = new Map(localFolderList.map(f => [f.id, f.name]));
        const localView = local.notes.filter(n => folderMatches(folder, 'local', n.folderId)).map(n => toViewLocal(n, id => localMap.get(id) || '—'));
        const serverView = serverNotes.filter(n => folderMatches(folder, 'server', n.folder_id == null ? '' : String(n.folder_id))).map(toViewServer);
        const merged = [...localView, ...serverView].sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
        if (revision !== loadRevision.current) return;
        setNotes(merged);
        setTags(Array.from(new Set([...local.tags, ...serverTags])).sort());
        setServerFolders(serverFolderList);
        setLocalFolders(localFolderList);
      }
    } catch (err) {
      if (revision === loadRevision.current) setError(err instanceof Error ? err.message : 'Не удалось загрузить заметки.');
    } finally {
      if (revision === loadRevision.current) setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    return () => { loadRevision.current += 1; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, search, folder, tag, format, noteAccessKey]);

  const switchTab = (next: Tab) => {
    setTab(next);
    setFolder('');
    setTag('');
  };

  const openCreate = () => {
    if (operationLock.current) return;
    editorScope.current = noteAccessKey;
    setLocalOnly(false);
    const chosen = folderSelection(folder);
    const server = tab === 'shared' || chosen.origin === 'server';
    setEditing({ uid: 'new', origin: server ? 'server' : 'local', id: '', title: '', content: '', format: 'html', tags: [], folderId: chosen.id === 'root' ? '' : chosen.id, folderName: null, is_public: tab === 'shared', username: null, is_owner: true, updated_at: '', deleted_at: null });
    setEditorOpen(true);
  };

  const openEdit = (note: ViewNote) => {
    if (operationLock.current) return;
    editorScope.current = noteAccessKey;
    setLocalOnly(false);
    setEditing(note);
    setEditorOpen(true);
  };

  const saveNote = async (data: Record<string, any>) => {
    if (editorScope.current !== noteAccessKey) throw new Error('Окружение или права изменились. Откройте заметку заново перед сохранением.');
    setSaving(true);
    setError('');
    if (localOnly) data = { ...data, is_public: false };
    try {
      if (localOnly) {
        await createLocalNote({ title: data.title, content: data.content, format: data.format, tags: data.tags, folderId: data.folder_id || '' });
      } else if (editing?.origin === 'server' && typeof editing.id === 'number') {
        await api.updateNote(editing.id, {
          title: data.title,
          content: data.content,
          format: data.format,
          tags: data.tags,
          is_public: data.is_public,
          folder_id: data.folder_id ? Number(data.folder_id) : null,
        });
      } else if (editing?.origin === 'local' && editing.id) {
        if (data.is_public) {
          // переезд локальной заметки на сервер
          await api.createNote({ title: data.title, content: data.content, format: data.format, tags: data.tags, is_public: true, folder_id: data.folder_id ? Number(data.folder_id) : null });
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
      } else if (data.is_public || editing?.origin === 'server') {
        await api.createNote({
          title: data.title,
          content: data.content,
          format: data.format,
          tags: data.tags,
          is_public: Boolean(data.is_public),
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
      setInventoryVersion(value => value + 1);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить заметку.');
      throw err;
    } finally {
      setSaving(false);
    }
  };

  const performBatch = async (targets: ViewNote[], action: (note: ViewNote) => Promise<void>) => {
    if (operationLock.current) return;
    operationLock.current = true; setBusy(true); setError(''); setNotice('');
    const scope = noteAccessKey;
    const workspace = getActiveWorkspaceId();
    const assertScope = () => {
      if (liveScope.current !== scope || getActiveWorkspaceId() !== workspace) throw new Error('Окружение или права изменились. Повторите операцию в исходном окружении.');
    };
    try {
      const result = await runNoteBatch(targets, async note => {
        assertScope();
        if (!note.is_owner) throw new Error('Можно изменять только свои заметки.');
        await action(note);
      });
      if (liveScope.current !== scope) return;
      setSelected(result.failed.map(f => f.item.uid));
      setInventoryVersion(value => value + 1);
      await load();
      if (liveScope.current !== scope) return;
      setNotice(`Обработано: ${result.completed.length} из ${targets.length}.`);
      if (result.failed.length) setError(result.failed.map(f => `${f.item.title}: ${f.message}`).join('\n'));
    } finally { operationLock.current = false; setBusy(false); }
  };
  const requestDelete = (targets: ViewNote[], permanent = false) => {
    setConfirmation({ title: permanent ? 'Удалить навсегда?' : 'Переместить в корзину?', message: `Заметок: ${targets.length}. ${permanent ? 'Восстановить их будет невозможно.' : 'Их можно будет восстановить из корзины.'}`, run: () => performBatch(targets, async note => {
      if (note.origin === 'local') await (permanent ? purgeLocalNote(String(note.id)) : softDeleteLocalNote(String(note.id)));
      else await api.deleteNote(Number(note.id), permanent);
    }) });
  };
  const moveToTrash = (note: ViewNote) => requestDelete([note]);
  const restore = (note: ViewNote) => performBatch([note], async item => {
    if (item.origin === 'local') await restoreLocalNote(String(item.id));
    else await api.restoreNote(Number(item.id));
  });
  const purge = (note: ViewNote) => requestDelete([note], true);
  const beginMove = (targets: ViewNote[]) => {
    if (busy) return;
    setDestination(`${targets[0]?.origin || 'local'}:root`); setMoving(targets);
  };
  const transfer = async () => {
    if (!moving) return;
    const chosen = folderSelection(destination);
    if (!chosen.origin) return;
    const target: NoteLocation = { origin: chosen.origin, folderId: chosen.id === 'root' ? '' : chosen.id };
    const scope = noteAccessKey; const workspace = getActiveWorkspaceId();
    const assertScope = () => {
      if (liveScope.current !== scope || workspace !== getActiveWorkspaceId()) throw new Error('Окружение или права изменились.');
    };
    let retained = 0;
    await performBatch(moving, async note => {
      const result = await moveNote(note, target, {
        assertScope,
        read: async source => {
          if (source.origin === 'server') {
            const current = await api.getNote(Number(source.id));
            return { ...current, origin: 'server' } as MovableNote;
          }
          const current = (await listLocalNotes()).notes.find(n => n.id === source.id);
          if (!current) throw new Error('Локальная заметка не найдена.');
          return { ...current, origin: 'local', is_owner: true };
        },
        move: (source, folderId) => source.origin === 'local' ? updateLocalNote(String(source.id), { folderId }) : api.updateNote(Number(source.id), { folder_id: folderId ? Number(folderId) : null }),
        create: (source, dest) => dest.origin === 'local'
          ? createLocalNote({ title: source.title, content: source.content, format: source.format, tags: source.tags, folderId: dest.folderId })
          : api.createNote({ title: source.title, content: source.content, format: source.format, tags: source.tags, folder_id: dest.folderId ? Number(dest.folderId) : null, is_public: false }),
        archive: source => source.origin === 'local' ? softDeleteLocalNote(String(source.id)) : api.deleteNote(Number(source.id)),
      });
      if (result.sourceRetained) retained++;
    });
    if (liveScope.current === scope) {
      setMoving(null);
      if (retained) setNotice(`Копии сохранены. Исходные записи (${retained}) не удалось отправить в корзину — они тоже сохранены. Не повторяйте перенос этих записей.`);
    }
  };

  const duplicate = (note: ViewNote) => performBatch([note], async note => {
      if (note.origin === 'local') await duplicateLocalNote(String(note.id));
      else if (typeof note.id === 'number') await api.duplicateNote(note.id);
  });

  const createFolder = async () => {
    if (operationLock.current) return;
    const name = newFolderName.trim();
    if (!name) return;
    try {
      const server = tab === 'shared' || newFolderOrigin === 'server';
      const created = server ? await api.createNoteFolder({ name }) : await createLocalFolder(name);
      setNewFolderName('');
      setFolderEditorOpen(false);
      setInventoryVersion(value => value + 1);
      await load();
      setFolder(`${server ? 'server' : 'local'}:${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать папку.');
    }
  };

  const removeFolder = async (id: string, name: string) => {
    setConfirmation({ title: 'Удалить папку?', message: `Папка «${name}» будет удалена. Заметки останутся без папки.`, run: async () => {
    if (operationLock.current) return;
    operationLock.current = true; setBusy(true);
    try {
      const selected = folderSelection(id);
      if (selected.origin === 'server') await api.deleteNoteFolder(Number(selected.id));
      else await deleteLocalFolder(selected.id);
      if (folder === id) setFolder('');
      setInventoryVersion(value => value + 1);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось удалить папку.');
    } finally { operationLock.current = false; setBusy(false); }
    } });
  };

  const folders = useMemo(() => [
    ...(tab === 'shared' ? [] : localFolders.map(f => ({ id: `local:${f.id}`, name: f.name, origin: 'local' as const }))),
    ...serverFolders.map(f => ({ id: `server:${f.id}`, name: f.name, origin: 'server' as const })),
  ], [tab, localFolders, serverFolders]);
  const folderName = useMemo(() => {
    const map = new Map(folders.map(f => [f.id, f.name]));
    return (id: string, origin: 'local' | 'server') => (id ? map.get(`${origin}:${id}`) || '—' : 'Без папки');
  }, [folders]);

  const hasFilters = search || folder || tag || format;

  return (
    <div className="mx-auto max-w-6xl space-y-4 pb-8" style={{ fontFamily: APPLE_FONT }}>
      <header className="relative overflow-visible">
        <div className="relative flex flex-col items-stretch gap-4 sm:flex-row sm:flex-wrap sm:items-end">
          <div className="min-w-0 sm:flex-1 sm:max-w-xl">
            <h2 className="tf-page-title">{sectionLabel('/notes')}</h2>
            <p className="tf-page-subtitle">
              Ваши записи, документы и идеи. Папки устройства и пространства — в одной библиотеке.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 sm:ml-auto">
            {!trash && (
              <button
                type="button"
                onClick={() => setFolderEditorOpen(prev => !prev)}
                className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-2.5 text-[15px] font-medium text-[var(--color-text)] transition hover:border-[var(--color-border-strong)] "
                style={{ boxShadow: 'var(--shadow-soft)' }}
              >
                <FolderPlus size={17} /> Папки
              </button>
            )}
            {!trash && (
              <button
                type="button"
                onClick={openCreate}
                className="inline-flex items-center gap-2 rounded-full px-6 py-2.5 text-[15px] font-semibold transition hover:opacity-90 "
                style={{ background: ACCENT, color: ON_ACCENT, boxShadow: 'var(--shadow-accent)' }}
              >
                <Plus size={17} strokeWidth={2.5} /> Новая заметка
              </button>
            )}
          </div>
        </div>
        <div className="relative mt-4 flex flex-wrap gap-2">
          <Pill active={tab === 'mine'} onClick={() => switchTab('mine')}><StickyNote size={15} /> Мои заметки</Pill>
          <Pill active={tab === 'shared'} onClick={() => switchTab('shared')}><Server size={15} /> Общие в окружении</Pill>
          <Pill active={tab === 'trash'} onClick={() => switchTab('trash')}><Trash2 size={15} /> Корзина</Pill>
        </div>
      </header>

      <div className="relative w-full">
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
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full px-5 py-2 text-[15px] font-semibold transition hover:opacity-90 "
          style={{ background: ACCENT, color: ON_ACCENT }}
        >
          Найти
        </button>
      </div>

      <div className="grid min-w-0 gap-5 lg:grid-cols-[240px_minmax(0,1fr)]">
        <aside className="min-w-0 space-y-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 lg:self-start">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">Библиотека</h3>
          <div className="lg:hidden"><Select value={folder} onChange={setFolder} label="Папка" options={[{ value: '', label: 'Все заметки' }, { value: 'root', label: 'Без папки' }, ...folders.map(f => ({ value: f.id, label: `${f.name} · ${f.origin === 'local' ? 'устройство' : 'сервер'}` }))]} /></div>
          <div className="hidden flex-col items-stretch gap-1 lg:flex [&>button]:justify-start [&>button]:text-left [&>button]:break-words">
            <Pill active={folder === ''} onClick={() => setFolder('')}>Все заметки</Pill>
            <Pill active={folder === 'root'} onClick={() => setFolder('root')}>Без папки</Pill>
            {(['local', 'server'] as const).map(origin => <div key={origin} className="mt-3 min-w-0 space-y-1 [&>button]:w-full [&>button]:justify-start [&>button]:text-left [&>button]:break-words">
              {(origin !== 'local' || tab !== 'shared') && <p className="px-3 py-2 text-xs font-semibold text-[var(--color-muted)]">{origin === 'local' ? 'На этом устройстве' : 'На сервере · мои папки'}</p>}
              {folders.filter(f => f.origin === origin).map(f => (
              <Pill key={f.id} active={folder === f.id} onClick={() => setFolder(folder === f.id ? '' : f.id)}>
                <span className="min-w-0 break-words">{f.name}</span>
              </Pill>
              ))}
            </div>)}
          </div>
          <p className="hidden border-t border-[var(--color-border)] pt-3 text-xs leading-relaxed text-[var(--color-muted)] lg:block">На устройстве — личные записи этого аккаунта, общие для его окружений. Серверные заметки — только из текущего окружения.</p>

          {folderEditorOpen && (
            <div className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6" style={{ boxShadow: 'var(--shadow-soft)' }}>
              <div className="text-sm font-semibold text-[var(--color-text)]">
                Новая папка
              </div>
              {tab !== 'shared' && <Select value={newFolderOrigin} onChange={setNewFolderOrigin} label="Хранение" options={[{ value: 'local', label: 'На устройстве' }, { value: 'server', label: 'На сервере' }]} />}
              <div className="mt-3 flex flex-wrap gap-3">
                <input
                  value={newFolderName}
                  onChange={event => setNewFolderName(event.target.value)}
                  onKeyDown={event => { if (event.key === 'Enter') void createFolder(); }}
                  placeholder="Название новой папки"
                  maxLength={200}
                  className="tf-input min-w-0 w-full sm:w-auto flex-1 rounded-full"
                />
                <button
                  type="button"
                  onClick={createFolder}
                  className="rounded-full px-6 py-2.5 text-[15px] font-semibold transition hover:opacity-90 "
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
        </aside>
        <section className="min-w-0 space-y-4" aria-label="Список заметок">

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

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
        <span className="text-sm text-[var(--color-muted)]">Заметок: {notes.length}</span>
        <div className="flex flex-wrap gap-2"><Select value={sort} onChange={setSort} label="Порядок" options={[{ value: 'updated', label: 'Сначала обновлённые' }, { value: 'title', label: 'По названию' }]} /><button className="tf-button" onClick={() => setView(view === 'list' ? 'cards' : 'list')}>{view === 'list' ? 'Карточки' : 'Список'}</button></div>
      </div>
      {notes.some(n => n.is_owner) && <div className="flex flex-wrap items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm">
        <label className="inline-flex items-center gap-2"><input type="checkbox" disabled={busy} checked={notes.filter(n => n.is_owner).every(n => selected.includes(n.uid))} onChange={event => setSelected(event.target.checked ? notes.filter(n => n.is_owner).map(n => n.uid) : [])} />Выбрать все свои</label>
        <span className="text-[var(--color-muted)]">Выбрано: {selected.length}</span>
        {selected.length > 0 && <>
          {!trash && <button type="button" disabled={busy} className="tf-button" onClick={() => beginMove(notes.filter(n => selected.includes(n.uid)))}><ArrowRightLeft size={15} />Перенести</button>}
          {trash && <button type="button" disabled={busy} className="tf-button" onClick={() => void performBatch(notes.filter(n => selected.includes(n.uid)), async note => { if (note.origin === 'local') await restoreLocalNote(String(note.id)); else await api.restoreNote(Number(note.id)); })}>Восстановить</button>}
          <button type="button" disabled={busy} className="tf-button text-[var(--color-danger)]" onClick={() => requestDelete(notes.filter(n => selected.includes(n.uid)), trash)}>{trash ? 'Удалить навсегда' : 'В корзину'}</button>
        </>}
        {busy && <span role="status">Обработка заметок…</span>}
      </div>}
      {notice && <p role="status" className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm">{notice}</p>}
      {error && (
        <div role="alert" className="whitespace-pre-line rounded-[20px] border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/[.07] px-6 py-4 text-[15px] font-medium text-[var(--color-danger)]">
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
            {trash ? 'Корзина пуста' : hasFilters ? 'Заметки не найдены' : 'Начните с первой заметки'}
          </p>
          <p className="mt-2 max-w-sm text-[15px] leading-relaxed text-[var(--color-text-secondary)]">
            {trash
              ? 'Удалённые заметки появятся здесь. Их можно восстановить или удалить навсегда.'
              : hasFilters ? 'В выбранной папке или по текущим фильтрам заметок нет. Можно сбросить фильтры или создать запись здесь.' : tab === 'shared'
                ? 'Отметьте заметку как общую — её увидят участники пространства с доступом к заметкам.'
                : 'Создайте первую заметку — идея, черновик или сниппет. Это займёт пару секунд.'}
          </p>
          {!trash && (
            <button
              type="button"
              onClick={openCreate}
              className="mt-7 inline-flex items-center gap-2 rounded-full px-7 py-3 text-[16px] font-semibold transition hover:opacity-90 "
              style={{ background: ACCENT, color: ON_ACCENT, boxShadow: 'var(--shadow-accent)' }}
            >
              <Plus size={17} strokeWidth={2.5} /> Создать заметку
            </button>
          )}
        </div>
      ) : (
        <div className={view === 'list' ? 'space-y-2' : 'grid grid-cols-1 gap-3 xl:grid-cols-2'}>
          {sortedNotes.map(note => (
            <article
              key={note.uid}
              onClick={() => !trash && openEdit(note)}
              tabIndex={trash ? undefined : 0}
              onKeyDown={event => { if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); if (!trash) openEdit(note); } }}
              className={cn(
                'group rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 focus-within:ring-2 focus-within:ring-[var(--color-ring)]',
                !trash && 'cursor-pointer',
              )}
              style={{ boxShadow: 'var(--shadow-soft)' }}
            >
              <div className="flex flex-wrap items-start gap-3 sm:flex-nowrap">
                {note.is_owner && <input type="checkbox" aria-label={`Выбрать заметку ${note.title}`} checked={selected.includes(note.uid)} disabled={busy} className="mt-1 shrink-0" onClick={event => event.stopPropagation()} onChange={event => setSelected(prev => event.target.checked ? [...prev, note.uid] : prev.filter(id => id !== note.uid))} />}
                <div className="min-w-0 flex-1">
                  <h3 className="line-clamp-2 break-words text-base font-semibold text-[var(--color-text)]">{note.title}</h3>
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-[var(--color-muted)]">
                    <OriginBadge note={note} />
                    <span>{NOTE_FORMATS[note.format] || note.format}</span>
                    <span>{note.folderName || folderName(note.folderId, note.origin)}</span>
                    {note.username && <span>· {note.username}</span>}
                  </div>
                </div>
                <div inert={busy || undefined} className="flex shrink-0 items-center gap-1.5 opacity-100 transition" onClick={event => event.stopPropagation()}>
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
                  {!trash && note.is_owner && (
                    <CircleButton onClick={() => beginMove([note])} title="Перенести заметку">
                      <ArrowRightLeft size={15} />
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
              <p className={cn('break-words text-sm leading-relaxed text-[var(--color-text-secondary)]', view === 'list' ? 'mt-2 line-clamp-2' : 'mt-4 line-clamp-3')}>
                {plainText(note.content).slice(0, 280) || 'Пустая заметка'}
              </p>
              <p className="mt-3 text-xs text-[var(--color-muted)]">
                Обновлена: {formatFullDate(note.updated_at)}
              </p>
            </article>
          ))}
        </div>
      )}

        </section>
      </div>
      {confirmation && <div className="fixed inset-0 z-[60] grid place-items-center bg-black/45 p-4">
        <section role="dialog" aria-modal="true" aria-labelledby="note-action-title" className="tf-modal-shell w-full max-w-md space-y-4 p-5">
          <h3 id="note-action-title" className="text-lg font-semibold">{confirmation.title}</h3>
          <p className="text-sm text-[var(--color-text-secondary)]">{confirmation.message}</p>
          <div className="flex justify-end gap-2"><button type="button" className="tf-button" onClick={() => setConfirmation(null)}>Отмена</button><button type="button" disabled={busy} className="tf-button tf-button-primary" onClick={() => { const action = confirmation.run; setConfirmation(null); void action(); }}>Подтвердить</button></div>
        </section>
      </div>}
      {moving && <div className="fixed inset-0 z-[60] grid place-items-center bg-black/45 p-4">
        <section role="dialog" aria-modal="true" aria-labelledby="note-move-title" className="tf-modal-shell w-full max-w-lg space-y-4 p-5">
          <h3 id="note-move-title" className="text-lg font-semibold">Перенести заметки · {moving.length}</h3>
          <Select disabled={busy} value={destination} onChange={setDestination} label="Куда перенести" options={[{ value: 'local:root', label: 'На устройство · без папки' }, ...localFolders.map(f => ({ value: `local:${f.id}`, label: `На устройство · ${f.name}` })), { value: 'server:root', label: 'На сервер · без папки' }, ...serverFolders.map(f => ({ value: `server:${f.id}`, label: `На сервер · ${f.name}` }))]} />
          <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">На сервере новые записи будут личными, в текущем окружении. При смене хранилища сначала сохраняется копия, затем оригинал перемещается в корзину. Локальные заметки не отправляются на сервер без вашего подтверждения.</p>
          <div className="flex justify-end gap-2"><button type="button" disabled={busy} className="tf-button" onClick={() => setMoving(null)}>Отмена</button><button type="button" disabled={busy} className="tf-button tf-button-primary" onClick={() => void transfer()}>{busy ? 'Перенос…' : 'Перенести'}</button></div>
        </section>
      </div>}
      {editorOpen && (
        <NoteModal
          key={editing?.uid || "new"}
          localOnly={localOnly}
          inventory={inventory}
          onNavigate={openEdit}
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
      aria-pressed={active}
      className={cn(
        'inline-flex max-w-full items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium',
        active ? '' : 'bg-[var(--color-overlay)] text-[var(--color-text-secondary)] hover:bg-[var(--color-overlay-strong)] hover:text-[var(--color-text)]',
      )}
      style={active ? { background: ACCENT, color: ON_ACCENT,  } : undefined}
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

function NoteModal({ localOnly = false, note, inventory, onNavigate, serverFolders, localFolders, saving, onClose, onSave }: {
  localOnly?: boolean;
  inventory: ViewNote[];
  onNavigate: (note: ViewNote) => void;
  note: ViewNote | null;
  serverFolders: NoteFolder[];
  localFolders: LocalFolder[];
  saving: boolean;
  onClose: () => void;
  onSave: (data: Record<string, any>) => Promise<void>;
}) {
  const readOnly = Boolean(note && !note.is_owner);
  const [title, setTitle] = useState(note?.title || '');
  const [content, setContent] = useState(note?.content || '');
  const [format, setFormat] = useState(note?.format || 'html');
  const [pendingFormat, setPendingFormat] = useState<string | null>(null);
  const [tags, setTags] = useState((note?.tags || []).join(', '));
  const [isPublic, setIsPublic] = useState(note ? note.is_public : false);
  const [folderId, setFolderId] = useState(note?.folderId || '');
  const [error, setError] = useState('');

  const origin: 'server' | 'local' = note?.origin === 'server' || isPublic ? 'server' : 'local';
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
    format: note?.format || 'html',
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
    if (saving) return;
    if (!isDirty || confirm('Есть несохранённые изменения. Закрыть без сохранения?')) onClose();
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    if (readOnly || saving) return;
    if (content.length > 100000) { setError('Максимальный размер заметки — 100 000 символов.'); return; }
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
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить заметку.');
    }
  };

  const links = linkedNotes({ uid: note?.uid || '', title, content }, inventory);
  const applyFormat = (next: string) => {
    if (next === format) return;
    const converted = convertNoteFormat(content, format, next);
    if (converted.length > 100000) { setError('После преобразования текст превышает 100 000 символов.'); return; }
    setContent(converted); setFormat(next); setPendingFormat(null); setError('');
  };
  const changeFormat = (next: string) => { if (next === format) return; if (content) setPendingFormat(next); else applyFormat(next); };
  const navigateNote = (target: ViewNote) => {
    if (!isDirty || confirm('Есть несохранённые изменения. Перейти без сохранения?')) onNavigate(target);
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/45 p-2 sm:p-5" onClick={requestClose} style={{ fontFamily: APPLE_FONT }}>
      <form
        onSubmit={submit}
        onKeyDown={event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); if (!readOnly && !saving) event.currentTarget.requestSubmit(); } }}
        role="dialog"
        aria-modal="true"
        aria-label={note?.id ? 'Редактирование заметки' : 'Новая заметка'}
        className="tf-modal-shell flex max-h-[96dvh] w-full max-w-5xl flex-col overflow-hidden"
        onClick={event => event.stopPropagation()}
      >
        <div className="flex shrink-0 items-center gap-3 px-4 pb-4 pt-4 sm:px-6">
          <h2 className="text-[24px] font-semibold tracking-tight text-[var(--color-text)]">
            {localOnly ? 'Локальный черновик' : note?.id ? 'Заметка' : 'Новая заметка'}
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

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 pb-3 sm:px-7">
          <fieldset disabled={readOnly} className="min-w-0 space-y-6">
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
                onClick={() => changeFormat(key)}
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
              disabled={localOnly}
              onClick={() => setIsPublic(prev => !prev)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-[13.5px] font-medium transition active:scale-[.97]',
                isPublic ? '' : 'bg-[var(--color-overlay)] text-[var(--color-text-secondary)] hover:bg-[var(--color-overlay-strong)] hover:text-[var(--color-text)]',
              )}
              style={isPublic ? { background: '#5f8f6a', color: '#fff' } : undefined}
              title={isPublic ? 'Хранится на сервере, видна участникам пространства' : origin === 'server' ? 'Личная заметка на сервере' : 'Хранится только на этом устройстве'}
            >
              {isPublic ? <Globe size={13} /> : <Lock size={13} />}
              {localOnly ? 'Только локально · черновик ИИ' : isPublic ? 'Общая' : 'Личная'}
            </button>
          </div>
          <p className="-mt-3 text-[13px] text-[var(--color-muted)]">
            {localOnly ? 'Локальная заметка. Сохранение на сервере отключено.' : isPublic
              ? 'Общая заметка хранится на сервере.'
              : origin === 'server'
                ? 'Серверная заметка. Кнопка «Скачать на ПК» в списке перенесёт её только на этот компьютер.'
                : 'Личная заметка хранится на этом ПК. Только выбранный вами и отправленный текст передаётся помощнику и остаётся в истории диалога.'}
          </p>
          {pendingFormat && <div role="alert" className="rounded-xl border border-[var(--color-border-strong)] bg-[var(--color-surface-2)] p-4 text-sm">
            <p>Преобразовать в «{NOTE_FORMATS[pendingFormat]}»? Сложное оформление, таблицы и чек-листы могут измениться. Сделайте копию заметки, если важно сохранить исходник.</p>
            <div className="mt-3 flex gap-2"><button type="button" className="tf-button tf-button-primary" onClick={() => applyFormat(pendingFormat)}>Преобразовать</button><button type="button" className="tf-button" onClick={() => setPendingFormat(null)}>Оставить формат</button></div>
          </div>}

          <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-overlay)] p-3"><h3 className="text-sm font-medium">Папка и теги</h3>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
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
                placeholder="идеи, учёба, проект"
                className="tf-input h-12 rounded-2xl text-[15px]"
              />
            </label>
          </div>
          </section>

          </fieldset>
          <div>
            {format === 'html' ? <RichTextEditor readOnly={readOnly || saving} value={content} onChange={setContent} minHeightClassName="min-h-64" label="Текст заметки" placeholder="Начните писать. Ссылка на заметку: [[Название]]" /> : <TextEditor value={content} onChange={setContent} readOnly={readOnly || saving} format={format as 'text' | 'markdown' | 'code'} label="Текст заметки" minHeightClassName="min-h-64" placeholder="Начните писать. Ссылка на заметку: [[Название]]" />}
          </div>
          <section className="rounded-xl border border-[var(--color-border)] p-4 text-sm">
            <h3 className="font-semibold">Связи между заметками</h3>
            <p className="mt-1 text-xs text-[var(--color-text-secondary)]">Добавьте [[Название заметки]] в текст. Здесь показаны связи с доступными вам заметками.</p>
            <div className="mt-3 flex flex-wrap gap-2">{links.outgoing.map(link => link.matches.length ? link.matches.map(target => <button key={target.uid} type="button" className="tf-button" onClick={() => navigateNote(target)}>{link.title}{link.matches.length > 1 ? ` · ${target.origin === 'local' ? 'на ПК' : 'сервер'} · ${target.id}` : ''}</button>) : <span key={link.title} className="tf-chip">{link.title} · не найдена</span>)}</div>
            <h4 className="mt-4 text-xs font-semibold">Ссылаются на эту заметку</h4>
            <div className="mt-2 flex flex-wrap gap-2">{links.incoming.map(target => <button key={target.uid} type="button" className="tf-button" onClick={() => navigateNote(target)}>{target.title}</button>)}{!links.incoming.length && <span className="text-xs text-[var(--color-muted)]">Пока нет обратных ссылок</span>}</div>
          </section>

          {error && <div className="text-[14.5px] font-medium text-[var(--color-danger)]">{error}</div>}
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-3 px-4 py-4 sm:px-6">
          <button
            type="button"
            onClick={requestClose}
            className="tf-button rounded-full px-6"
          >
            Отмена
          </button>
          <button
            type="submit"
            disabled={saving || readOnly}
            className="rounded-full px-8 py-2.5 text-[15px] font-semibold transition hover:opacity-90  disabled:opacity-60"
            style={{ background: ACCENT, color: ON_ACCENT, boxShadow: 'var(--shadow-accent)' }}
          >
            {saving ? 'Сохранение...' : localOnly ? 'Сохранить на устройстве' : note ? 'Сохранить' : 'Создать'}
          </button>
          {!readOnly && <span className="hidden text-xs text-[var(--color-muted)] sm:inline">Ctrl+S — сохранить</span>}
        </div>
      </form>
    </div>
  );
}

function plainText(html: string): string {
  return (html || '').replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
}
