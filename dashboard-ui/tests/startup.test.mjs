import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
const source = await readFile(new URL('../public/startup.js', import.meta.url), 'utf8');
function boot({ ready = false, blocked = false, storage = new Map() } = {}) {
  const events = {}, timers = [], notices = [];
  let reloads = 0;
  const root = { dataset: ready ? { boot: 'ready' } : {} };
  const document = {
    documentElement: { dataset: {} },
    getElementById: () => root,
    body: { appendChild: element => notices.push(element) },
    createElement: tag => ({ tag, style: {}, setAttribute() {}, append(...children) { this.children = children; } }),
    addEventListener: (name, callback) => { events[name] = callback; },
  };
  vm.runInNewContext(source, {
    document, window: { addEventListener: (name, callback) => { events[name] = callback; } },
    location: { href: 'http://taskflow.local/tasks', reload: () => { reloads++; } }, URL, Date,
    localStorage: { getItem: () => null },
    sessionStorage: { getItem: key => { if (blocked) throw Error('blocked'); return storage.get(key); }, setItem: (key, value) => storage.set(key, value) },
    setTimeout: callback => timers.push(callback),
  });
  return { events, notices, timers, root, reloads: () => reloads };
}
const missing = { target: { tagName: 'SCRIPT', src: 'http://taskflow.local/assets/old.js' } };
test('missing entry bundle retries once across reloads, then shows recovery', () => {
  const storage = new Map(); const first = boot({ storage }); first.events.error(missing);
  assert.equal(first.reloads(), 1);
  const second = boot({ storage }); second.events.error(missing); second.events.error(missing);
  assert.equal(second.reloads(), 0); assert.equal(second.notices.length, 1);
});
test('failed lazy import after startup never discards an open form automatically', () => {
  const app = boot({ ready: true }); let prevented = false;
  app.events['vite:preloadError']({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true); assert.equal(app.reloads(), 0); assert.equal(app.notices.length, 1);
  app.notices[0].children[1].onclick(); assert.equal(app.reloads(), 1);
});
test('blocked storage cannot cause a reload loop', () => {
  const app = boot({ blocked: true }); app.events.error(missing);
  assert.equal(app.reloads(), 0); assert.equal(app.notices.length, 1);
});
test('stalled startup shows a message, completed startup does not', () => {
  const stalled = boot(); stalled.events.DOMContentLoaded(); stalled.timers[0]();
  assert.equal(stalled.notices.length, 1);
  const loaded = boot({ ready: true }); loaded.events.DOMContentLoaded(); loaded.timers[0]();
  assert.equal(loaded.notices.length, 0);
});
test('ordinary runtime rejection does not cause a reload', () => {
  const app = boot(); app.events.unhandledrejection({ reason: new Error('API network error') });
  assert.equal(app.reloads(), 0); assert.equal(app.notices.length, 0);
});
