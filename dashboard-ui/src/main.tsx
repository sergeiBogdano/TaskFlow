import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { AppErrorBoundary } from './components/AppErrorBoundary';
import './index.css';
import { applyTheme, getTheme } from './lib/theme';

applyTheme(getTheme());

const root = document.getElementById('root')!;
root.dataset.boot = 'ready';
createRoot(root).render(
  <StrictMode>
    <AppErrorBoundary><App /></AppErrorBoundary>
  </StrictMode>
);
