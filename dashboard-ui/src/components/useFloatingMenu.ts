import { floatingMenuPlacement } from '../lib/floatingMenu';
import { useLayoutEffect, useState, type CSSProperties, type RefObject } from 'react';

/** Position above/below the anchor without clipping in dialogs or small viewports. */
export function useFloatingMenu(open: boolean, anchorRef: RefObject<HTMLElement | null>, minWidth = 180) {
  const [style, setStyle] = useState<CSSProperties>({ visibility: 'hidden', position: 'fixed' });
  useLayoutEffect(() => {
    if (!open) return;
    const update = () => {
      const anchor = anchorRef.current;
      if (!anchor) return;
      const rect = anchor.getBoundingClientRect();
      const viewport = window.visualViewport;
      const x = viewport?.offsetLeft || 0;
      const y = viewport?.offsetTop || 0;
      const width = viewport?.width || window.innerWidth;
      const height = viewport?.height || window.innerHeight;
      setStyle(floatingMenuPlacement(rect, { x, y, width, height, layoutHeight: window.innerHeight }, minWidth));
    };
    update();
    const observer = new ResizeObserver(update);
    if (anchorRef.current) observer.observe(anchorRef.current);
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    window.visualViewport?.addEventListener('resize', update);
    window.visualViewport?.addEventListener('scroll', update);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
      window.visualViewport?.removeEventListener('resize', update);
      window.visualViewport?.removeEventListener('scroll', update);
    };
  }, [open, anchorRef, minWidth]);
  return style;
}
