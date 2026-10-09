import test from 'node:test';
import assert from 'node:assert/strict';
import { floatingMenuPlacement } from '../src/lib/floatingMenu.ts';
const viewport = { x: 0, y: 0, width: 320, height: 600, layoutHeight: 600 };
test('long and wide dropdowns remain inside a narrow screen', () => {
  const menu = floatingMenuPlacement({ left: 250, top: 100, bottom: 140, width: 500 }, viewport);
  assert.equal(menu.width, 300); assert.equal(menu.left, 10);
  assert.equal(menu.top, 146); assert.equal(menu.maxHeight, 360);
});
test('menus open above a low trigger, aligned with the trigger', () => {
  const menu = floatingMenuPlacement({ left: 20, top: 530, bottom: 570, width: 200 }, viewport);
  assert.equal(menu.bottom, 76); assert.equal(menu.top, undefined);
  assert.equal(menu.maxHeight, 360);
});
test('keyboard and zoom offsets constrain the menu to the visible viewport', () => {
  const menu = floatingMenuPlacement({ left: 400, top: 420, bottom: 460, width: 250 }, { x: 100, y: 200, width: 240, height: 300, layoutHeight: 800 });
  assert.equal(menu.left, 110); assert.equal(menu.width, 220);
  assert.equal(menu.bottom, 386); assert.equal(menu.maxHeight, 204);
});
test('a scrolled away trigger cannot leave an invisible off-screen menu', () => {
  const menu = floatingMenuPlacement({ left: 20, top: 2000, bottom: 2040, width: 200 }, viewport);
  assert.equal(menu.visibility, 'hidden'); assert.ok(menu.maxHeight >= 0);
});
