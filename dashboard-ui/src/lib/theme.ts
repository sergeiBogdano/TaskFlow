export type ThemeName = 'cream' | 'graphite';

const KEY = 'taskflow:theme';

export function getTheme(): ThemeName {
  try {
    const stored = localStorage.getItem(KEY);
    return stored === 'graphite' ? stored : 'cream';
  } catch {
    return 'cream';
  }
}

export function applyTheme(name: ThemeName): void {
  if (name !== 'cream') {
    document.documentElement.dataset.theme = name;
  } else {
    delete document.documentElement.dataset.theme;
  }
  try {
    localStorage.setItem(KEY, name);
  } catch {
    /* ignore */
  }
}
