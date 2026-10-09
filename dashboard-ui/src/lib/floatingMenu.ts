type Anchor = { left: number; top: number; bottom: number; width: number };
type Viewport = { x: number; y: number; width: number; height: number; layoutHeight: number };

/** Keep portalled menus inside the visible screen, including an on-screen keyboard. */
export function floatingMenuPlacement(rect: Anchor, viewport: Viewport, minWidth = 180) {
  const { x, y, width, height, layoutHeight } = viewport;
  const padding = Math.min(10, width / 4, height / 4), gap = 6;
  const menuWidth = Math.max(0, Math.min(Math.max(rect.width, minWidth), width - padding * 2));
  const anchorTop = Math.max(y + padding, Math.min(rect.top, y + height - padding));
  const anchorBottom = Math.max(y + padding, Math.min(rect.bottom, y + height - padding));
  const below = Math.max(0, y + height - anchorBottom - gap - padding);
  const above = Math.max(0, anchorTop - y - gap - padding);
  const opensUp = below < 280 && above > below;
  return {
    position: 'fixed' as const,
    visibility: rect.bottom <= y || rect.top >= y + height ? 'hidden' as const : 'visible' as const,
    left: Math.max(x + padding, Math.min(rect.left, x + width - menuWidth - padding)),
    width: menuWidth,
    maxHeight: Math.min(360, opensUp ? above : below),
    ...(opensUp ? { bottom: layoutHeight - anchorTop + gap } : { top: anchorBottom + gap }),
  };
}
