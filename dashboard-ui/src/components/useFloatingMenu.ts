import { useCallback, useLayoutEffect, useState, type CSSProperties, type RefObject } from 'react';

type MenuStyle = CSSProperties & { '--tf-menu-width'?: string };

/** Positions a menu in the document layer so sidebar/card overflow cannot clip it. */
export function useFloatingMenu(
  open: boolean,
  anchorRef: RefObject<HTMLElement | null>,
  minWidth = 180,
) {
  const [style, setStyle] = useState<MenuStyle>();

  const update = useCallback(() => {
    const anchor = anchorRef.current;
    if (!anchor || !open) return;
    const rect = anchor.getBoundingClientRect();
    const viewportPadding = 10;
    const width = Math.max(rect.width, minWidth);
    const left = Math.max(viewportPadding, Math.min(rect.left, window.innerWidth - width - viewportPadding));
    const availableBelow = window.innerHeight - rect.bottom - viewportPadding;
    const availableAbove = rect.top - viewportPadding;
    const opensUp = availableBelow < 280 && availableAbove > availableBelow;
    const top = opensUp
      ? Math.max(viewportPadding, rect.top - 6 - Math.min(360, availableAbove))
      : Math.min(window.innerHeight - viewportPadding, rect.bottom + 6);
    setStyle({
      position: 'fixed',
      left,
      top,
      width,
      maxWidth: `calc(100vw - ${viewportPadding * 2}px)`,
      maxHeight: `calc(100vh - ${viewportPadding * 2}px)`,
      '--tf-menu-width': `${width}px`,
    });
  }, [anchorRef, minWidth, open]);

  useLayoutEffect(() => {
    if (!open) {
      setStyle(undefined);
      return;
    }
    const frame = requestAnimationFrame(update);
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [open, update]);

  return style;
}
