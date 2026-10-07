import test from 'node:test';
import assert from 'node:assert/strict';
import { dateInputValue, shiftCalendarDate } from '../src/lib/dates.ts';

test('date inputs preserve local calendar boundaries in both UTC offsets', () => {
  const previous = process.env.TZ;
  try {
    for (const timezone of ['UTC', 'Asia/Yerevan', 'America/Los_Angeles']) {
      process.env.TZ = timezone;
      assert.equal(dateInputValue(new Date(2026, 9, 1)), '2026-10-01');
      assert.equal(dateInputValue(new Date(2026, 9, 31, 23, 59)), '2026-10-31');
    }
  } finally { if (previous === undefined) delete process.env.TZ; else process.env.TZ = previous; }
});

test('month navigation cannot skip February from January 31', () => {
  const date = new Date(2026, 0, 31);
  assert.equal(dateInputValue(shiftCalendarDate(date, 1, true)), '2026-02-01');
  assert.equal(dateInputValue(shiftCalendarDate(date, -1, true)), '2025-12-01');
  assert.equal(dateInputValue(date), '2026-01-31');
});

test('day navigation handles leap days and year boundaries', () => {
  assert.equal(dateInputValue(shiftCalendarDate(new Date(2024, 1, 28), 1, false)), '2024-02-29');
  assert.equal(dateInputValue(shiftCalendarDate(new Date(2026, 11, 31), 1, false)), '2027-01-01');
});
