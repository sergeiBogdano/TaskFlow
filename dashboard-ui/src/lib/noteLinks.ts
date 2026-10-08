/** Wiki links are names, never executable HTML or URLs. */
export function noteLinks(content: string): string[] {
  return [...new Set(Array.from(content.matchAll(/\[\[([^[\]\n]{1,200})\]\]/g), match => match[1].split('|')[0].trim()).filter(Boolean))];
}

export function linkedNotes<T extends { uid: string; title: string; content: string }>(current: { uid: string; title: string; content: string }, inventory: T[]) {
  const targets = noteLinks(current.content);
  return {
    outgoing: targets.map(title => ({ title, matches: inventory.filter(note => note.uid !== current.uid && note.title === title) })),
    incoming: inventory.filter(note => note.uid !== current.uid && noteLinks(note.content).includes(current.title)),
  };
}
