export type NoteLocation = { origin: 'local' | 'server'; folderId: string };
export type MovableNote = { id: string | number; origin: 'local' | 'server'; is_owner: boolean; title: string; content: string; format: string; tags: string[] };
export type NoteMovePorts = {
  read: (note: MovableNote) => Promise<MovableNote>;
  move: (note: MovableNote, folderId: string) => Promise<unknown>;
  create: (note: MovableNote, destination: NoteLocation) => Promise<unknown>;
  archive: (note: MovableNote) => Promise<unknown>;
  assertScope: () => void;
};

// Cross-storage moves commit the destination before touching the source.
// Keep the source in trash for recovery; a failed archive must never lose data.
export async function moveNote(note: MovableNote, destination: NoteLocation, ports: NoteMovePorts) {
  if (!note.is_owner) throw new Error('Можно переносить только свои заметки.');
  ports.assertScope();
  if (note.origin === destination.origin) {
    await ports.move(note, destination.folderId);
    return { sourceRetained: false };
  }
  const current = await ports.read(note);
  ports.assertScope();
  if (!current.is_owner) throw new Error('Доступ к заметке изменился.');
  await ports.create(current, destination);
  try {
    ports.assertScope();
    await ports.archive(note);
    return { sourceRetained: false };
  } catch {
    return { sourceRetained: true };
  }
}

export async function runNoteBatch<T>(items: T[], action: (item: T) => Promise<void>) {
  const completed: T[] = [];
  const failed: { item: T; message: string }[] = [];
  // Local IndexedDB storage updates the note collection as a whole. Never race writes.
  for (const item of items) {
    try { await action(item); completed.push(item); }
    catch (error) { failed.push({ item, message: error instanceof Error ? error.message : 'Операция не выполнена.' }); }
  }
  return { completed, failed };
}
