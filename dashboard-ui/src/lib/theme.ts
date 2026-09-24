export type ThemeName = 'cream' | 'graphite';

const KEY = 'taskflow:theme';

export function getTheme(): ThemeName {
  try {
    return localStorage.getItem(KEY) === 'graphite' ? 'graphite' : 'cream';
  } catch {
    return 'cream';
  }
}

export function applyTheme(name: ThemeName): void {
  if (name === 'graphite') {
    document.documentElement.dataset.theme = 'graphite';
  } else {
    delete document.documentElement.dataset.theme;
  }
  try {
    localStorage.setItem(KEY, name);
  } catch {
    /* ignore */
  }
}
