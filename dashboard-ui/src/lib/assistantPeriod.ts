export type AssistantPeriod = { date_start: string; date_end: string };
function iso(day: Date) { return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`; }
export function monthPeriod(offset = 0, now = new Date(), timezone?: string): AssistantPeriod {
  if (timezone) { const parts = new Intl.DateTimeFormat('en', { timeZone: timezone, year: 'numeric', month: 'numeric' }).formatToParts(now); const year = Number(parts.find(part => part.type === 'year')?.value); const month = Number(parts.find(part => part.type === 'month')?.value); now = new Date(year, month - 1, 15, 12); }
  return { date_start: iso(new Date(now.getFullYear(), now.getMonth() + offset, 1)), date_end: iso(new Date(now.getFullYear(), now.getMonth() + offset + 1, 0)) };
}
export function periodError(period: AssistantPeriod) {
  const parse = (value: string) => { if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return NaN; const time = Date.parse(value + 'T00:00:00Z'); return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value ? time : NaN; };
  const start = parse(period.date_start), end = parse(period.date_end);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return 'Укажите обе даты периода.';
  if (end < start) return 'Конец периода не может быть раньше начала.';
  if ((end - start) / 86400000 >= 31) return 'Максимум — 31 календарный день включительно.';
  return '';
}
export function periodLastDay(start: string) { const time = Date.parse(start + 'T00:00:00Z'); return Number.isFinite(time) ? new Date(time + 30 * 86400000).toISOString().slice(0, 10) : undefined; }
