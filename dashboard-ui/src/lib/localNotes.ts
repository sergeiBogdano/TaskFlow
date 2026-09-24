// Локальное хранилище ЛИЧНЫХ заметок — никогда не покидает ПК.
// Приоритет: выбранная пользователем папка (File System Access API),
// запасной вариант: встроенное хранилище браузера (IndexedDB).

export type LocalNote = {
  id: string;
  title: string;
  content: string;
  format: string;
  tags: string[];
  folderId: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

export type LocalFolder = {
  id: string;
  name: string;
};

export type LocalStorageInfo = {
  supported: boolean;
  mode: 'dir' | 'browser';
  dirName: string | null;
};

function uid(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `n-${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
  }
}

function nowIso(): string {
  return new Date().toISOString();
}

// ---------- IndexedDB (ключ-значение + хранение handle папки) ----------

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('taskflow-local-notes', 1);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains('kv')) req.result.createObjectStore('kv');
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idbGet<T>(key: string): Promise<T | null> {
  try {
    const db = await openDb();
    return await new Promise<T | null>((resolve, reject) => {
      const tx = db.transaction('kv', 'readonly');
      const q = tx.objectStore('kv').get(key);
      q.onsuccess = () => resolve((q.result as T) ?? null);
      q.onerror = () => reject(q.error);
    });
  } catch {
    return null;
  }
}

async function idbSet(key: string, value: unknown): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction('kv', 'readwrite');
    const q = tx.objectStore('kv').put(value, key);
    q.onsuccess = () => resolve();
    q.onerror = () => reject(q.error);
  });
}

async function idbDel(key: string): Promise<void> {
  try {
    const db = await openDb();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction('kv', 'readwrite');
      const q = tx.objectStore('kv').delete(key);
      q.onsuccess = () => resolve();
      q.onerror = () => reject(q.error);
    });
  } catch {
    /* ignore */
  }
}

// ---------- Папка на ПК ----------

export function isDirPickerSupported(): boolean {
  return typeof window !== 'undefined' && typeof (window as any).showDirectoryPicker === 'function';
}

async function loadDirHandle(): Promise<any | null> {
  const handle = await idbGet<any>('notesDir');
  if (!handle) return null;
  try {
    const opts = { mode: 'readwrite' };
    if (typeof handle.queryPermission === 'function') {
      const granted = await handle.queryPermission(opts);
      if (granted !== 'granted') return null;
    }
    return handle;
  } catch {
    return null;
  }
}

export async function pickNotesDirectory(): Promise<string> {
  if (!isDirPickerSupported()) throw new Error('Браузер не поддерживает выбор папки. Будет использовано встроенное хранилище.');
  const handle = await (window as any).showDirectoryPicker({ mode: 'readwrite', startIn: 'documents' });
  if (handle && typeof handle.requestPermission === 'function') {
    const granted = await handle.requestPermission({ mode: 'readwrite' });
    if (granted !== 'granted') throw new Error('Нет доступа к папке.');
  }
  await idbSet('notesDir', handle);
  await idbSet('notesDirName', String(handle?.name || ''));
  // Переносим заметки из встроенного хранилища в папку при первом выборе
  await migrateFallbackToDir(handle);
  return String(handle?.name || '');
}

export async function disconnectNotesDirectory(): Promise<void> {
  await idbDel('notesDir');
  await idbDel('notesDirName');
}

export async function storageInfo(): Promise<LocalStorageInfo> {
  const supported = isDirPickerSupported();
  const handle = supported ? await loadDirHandle() : null;
  if (handle) {
    const name = (await idbGet<string>('notesDirName')) || String(handle?.name || '');
    return { supported, mode: 'dir', dirName: name || null };
  }
  return { supported, mode: 'browser', dirName: null };
}

// ---------- Формат файла: Markdown + JSON-шапка ----------

function serialize(note: LocalNote): string {
  const head = JSON.stringify({
    title: note.title,
    tags: note.tags,
    format: note.format,
    folderId: note.folderId,
    created_at: note.created_at,
    updated_at: note.updated_at,
    deleted_at: note.deleted_at,
  });
  return `---json\n${head}\n---\n${note.content || ''}`;
}

function parseFile(fileName: string, text: string): LocalNote | null {
  try {
    const id = fileName.replace(/\.md$/i, '');
    if (!id) return null;
    const lines = text.split('\n');
    if (lines[0]?.trim() !== '---json') {
      return { id, title: id, content: text, format: 'markdown', tags: [], folderId: '', created_at: nowIso(), updated_at: nowIso(), deleted_at: null };
    }
    const head = JSON.parse(lines[1] || '{}');
    const sepIndex = lines.findIndex((line, i) => i > 1 && line.trim() === '---');
    const content = sepIndex >= 0 ? lines.slice(sepIndex + 1).join('\n') : '';
    return {
      id,
      title: String(head.title || id),
      content,
      format: String(head.format || 'markdown'),
      tags: Array.isArray(head.tags) ? head.tags.map(String) : [],
      folderId: String(head.folderId || ''),
      created_at: String(head.created_at || nowIso()),
      updated_at: String(head.updated_at || nowIso()),
      deleted_at: head.deleted_at ? String(head.deleted_at) : null,
    };
  } catch {
    return null;
  }
}

async function readAllFromDir(dir: any): Promise<LocalNote[]> {
  const notes: LocalNote[] = [];
  try {
    for await (const entry of dir.values()) {
      if (entry && entry.kind === 'file' && typeof entry.name === 'string' && entry.name.toLowerCase().endsWith('.md')) {
        try {
          const file = await entry.getFile();
          const text = await file.text();
          const note = parseFile(entry.name, text);
          if (note) notes.push(note);
        } catch {
          /* пропускаем нечитаемые файлы */
        }
      }
    }
  } catch {
    /* ignore */
  }
  return notes;
}

async function writeToDir(dir: any, note: LocalNote): Promise<void> {
  const fileHandle = await dir.getFileHandle(`${note.id}.md`, { create: true });
  const writable = await fileHandle.createWritable();
  await writable.write(serialize(note));
  await writable.close();
}

async function removeFromDir(dir: any, id: string): Promise<void> {
  try {
    await dir.removeEntry(`${id}.md`);
  } catch {
    /* ignore */
  }
}

async function migrateFallbackToDir(dir: any): Promise<void> {
  const fallback = await idbGet<LocalNote[]>('notesFallback');
  if (!fallback || !fallback.length) return;
  for (const note of fallback) {
    try {
      await writeToDir(dir, note);
    } catch {
      /* ignore */
    }
  }
  await idbDel('notesFallback');
}

// ---------- CRUD ----------

export type LocalListOpts = {
  q?: string;
  folderId?: string;
  tag?: string;
  format?: string;
  trash?: boolean;
};

function applyFilters(notes: LocalNote[], opts: LocalListOpts): LocalNote[] {
  const q = (opts.q || '').trim().toLowerCase();
  return notes
    .filter(n => (opts.trash ? n.deleted_at !== null : n.deleted_at === null))
    .filter(n => (!opts.folderId ? true : opts.folderId === 'root' ? !n.folderId : n.folderId === opts.folderId))
    .filter(n => (!opts.tag ? true : n.tags.includes(opts.tag!)))
    .filter(n => (!opts.format ? true : n.format === opts.format))
    .filter(n => {
      if (!q) return true;
      return n.title.toLowerCase().includes(q) || n.content.toLowerCase().includes(q) || n.tags.join(' ').toLowerCase().includes(q);
    })
    .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
}

export async function listLocalNotes(opts: LocalListOpts = {}): Promise<{ notes: LocalNote[]; tags: string[]; total: number }> {
  const dir = await loadDirHandle();
  const all = dir ? await readAllFromDir(dir) : ((await idbGet<LocalNote[]>('notesFallback')) || []);
  const tags = Array.from(new Set(all.filter(n => !n.deleted_at).flatMap(n => n.tags))).sort();
  const notes = applyFilters(all, opts);
  return { notes, tags, total: notes.length };
}

export async function createLocalNote(data: { title: string; content: string; format: string; tags: string[]; folderId: string }): Promise<LocalNote> {
  const note: LocalNote = {
    id: uid(),
    title: data.title.trim() || 'Новая заметка',
    content: data.content || '',
    format: data.format || 'markdown',
    tags: data.tags || [],
    folderId: data.folderId || '',
    created_at: nowIso(),
    updated_at: nowIso(),
    deleted_at: null,
  };
  const dir = await loadDirHandle();
  if (dir) {
    await writeToDir(dir, note);
  } else {
    const all = (await idbGet<LocalNote[]>('notesFallback')) || [];
    all.push(note);
    await idbSet('notesFallback', all);
  }
  return note;
}

export async function updateLocalNote(id: string, patch: Partial<Omit<LocalNote, 'id' | 'created_at'>>): Promise<LocalNote> {
  const dir = await loadDirHandle();
  if (dir) {
    const all = await readAllFromDir(dir);
    const note = all.find(n => n.id === id);
    if (!note) throw new Error('Заметка не найдена.');
    const next = { ...note, ...patch, id: note.id, created_at: note.created_at, updated_at: nowIso() };
    await writeToDir(dir, next);
    return next;
  }
  const all = (await idbGet<LocalNote[]>('notesFallback')) || [];
  const index = all.findIndex(n => n.id === id);
  if (index < 0) throw new Error('Заметка не найдена.');
  const next = { ...all[index], ...patch, id: all[index].id, created_at: all[index].created_at, updated_at: nowIso() };
  all[index] = next;
  await idbSet('notesFallback', all);
  return next;
}

export async function softDeleteLocalNote(id: string): Promise<void> {
  await updateLocalNote(id, { deleted_at: nowIso() });
}

export async function restoreLocalNote(id: string): Promise<LocalNote> {
  return updateLocalNote(id, { deleted_at: null });
}

export async function purgeLocalNote(id: string): Promise<void> {
  const dir = await loadDirHandle();
  if (dir) {
    await removeFromDir(dir, id);
    return;
  }
  const all = (await idbGet<LocalNote[]>('notesFallback')) || [];
  await idbSet('notesFallback', all.filter(n => n.id !== id));
}

export async function duplicateLocalNote(id: string): Promise<LocalNote> {
  const dir = await loadDirHandle();
  const all = dir ? await readAllFromDir(dir) : ((await idbGet<LocalNote[]>('notesFallback')) || []);
  const src = all.find(n => n.id === id);
  if (!src) throw new Error('Заметка не найдена.');
  return createLocalNote({
    title: `${src.title} (копия)`.slice(0, 200),
    content: src.content,
    format: src.format,
    tags: [...src.tags],
    folderId: src.folderId,
  });
}

// ---------- Локальные папки ----------

export async function listLocalFolders(): Promise<LocalFolder[]> {
  const folders = (await idbGet<LocalFolder[]>('noteFolders')) || [];
  return [...folders].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
}

export async function createLocalFolder(name: string): Promise<LocalFolder> {
  const clean = name.trim().slice(0, 200);
  if (!clean) throw new Error('Название папки не может быть пустым.');
  const folders = (await idbGet<LocalFolder[]>('noteFolders')) || [];
  const folder = { id: uid(), name: clean };
  folders.push(folder);
  await idbSet('noteFolders', folders);
  return folder;
}

export async function deleteLocalFolder(id: string): Promise<void> {
  const folders = (await idbGet<LocalFolder[]>('noteFolders')) || [];
  await idbSet('noteFolders', folders.filter(f => f.id !== id));
  // Заметки остаются, папка у них сбрасывается
  const dir = await loadDirHandle();
  if (dir) {
    const all = await readAllFromDir(dir);
    for (const note of all.filter(n => n.folderId === id)) {
      await writeToDir(dir, { ...note, folderId: '', updated_at: nowIso() });
    }
  } else {
    const all = (await idbGet<LocalNote[]>('notesFallback')) || [];
    await idbSet('notesFallback', all.map(n => (n.folderId === id ? { ...n, folderId: '', updated_at: nowIso() } : n)));
  }
}
