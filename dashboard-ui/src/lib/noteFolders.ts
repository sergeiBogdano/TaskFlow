export function folderSelection(value: string): { origin: 'local' | 'server' | null; id: string } {
  if (!value || value === 'root') return { origin: null, id: value };
  if (value.startsWith('local:')) return { origin: 'local', id: value.slice(6) };
  if (value.startsWith('server:')) return { origin: 'server', id: value.slice(7) };
  return { origin: null, id: '' };
}

export function folderMatches(selection: string, origin: 'local' | 'server', id: string): boolean {
  const chosen = folderSelection(selection);
  if (chosen.origin && chosen.origin !== origin) return false;
  return !chosen.id || (chosen.id === 'root' ? !id : chosen.id === id);
}
