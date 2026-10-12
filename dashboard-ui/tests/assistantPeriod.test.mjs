import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const source = await readFile(new URL('../src/lib/assistantPeriod.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText;
const { monthPeriod, periodError, periodLastDay } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
test('calendar presets handle leap February and January rollover', () => {
 assert.deepEqual(monthPeriod(-1, new Date(2024, 2, 31)), { date_start: '2024-02-01', date_end: '2024-02-29' });
 assert.deepEqual(monthPeriod(-1, new Date(2026, 0, 20)), { date_start: '2025-12-01', date_end: '2025-12-31' });
});
test('31 inclusive days accepted, 32 rejected, invalid/reversed dates rejected', () => {
 assert.equal(periodError({date_start:'2026-01-01',date_end:'2026-01-31'}), '');
 for(const period of [{date_start:'2026-01-01',date_end:'2026-02-01'},{date_start:'2026-02-30',date_end:'2026-03-01'},{date_start:'2026-03-02',date_end:'2026-03-01'}]) assert.notEqual(periodError(period), '');
 assert.equal(periodLastDay('2026-01-01'), '2026-01-31');
});

test('presets use application timezone across the year boundary', () => {
 const instant = new Date('2025-12-31T22:00:00Z');
 assert.deepEqual(monthPeriod(0, instant, 'Europe/Moscow'), { date_start:'2026-01-01', date_end:'2026-01-31' });
 assert.deepEqual(monthPeriod(0, instant, 'America/Los_Angeles'), { date_start:'2025-12-01', date_end:'2025-12-31' });
});
