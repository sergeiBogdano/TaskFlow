import { Component, type ReactNode } from 'react';

export class AppErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <main className="mx-auto max-w-xl space-y-4 p-6" role="alert">
      <h1 className="text-xl font-semibold">Не удалось открыть приложение</h1>
      <p>Произошла ошибка загрузки интерфейса. Попробуйте обновить страницу. Несохранённые изменения могут быть потеряны.</p>
      <button className="tf-button tf-button-primary" onClick={() => window.location.reload()}>Обновить страницу</button>
    </main>;
    return this.props.children;
  }
}
