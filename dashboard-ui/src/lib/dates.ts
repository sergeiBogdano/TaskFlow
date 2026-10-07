/** Date-only inputs use the user's local calendar, never a UTC conversion. */
export function dateInputValue(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export function shiftCalendarDate(date: Date, direction: number, monthly: boolean): Date {
  const next = new Date(date);
  if (monthly) { next.setDate(1); next.setMonth(next.getMonth() + direction); }
  else next.setDate(next.getDate() + direction);
  return next;
}
