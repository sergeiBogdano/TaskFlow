export async function withRequestDeadline<T>(operation: (signal: AbortSignal) => Promise<T>, timeout = 15000): Promise<T> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout>;
  const expired = new Promise<never>((_, reject) => {
    timer = setTimeout(() => { controller.abort(); reject(new Error('Сервер не ответил вовремя. Повторите загрузку.')); }, timeout);
  });
  try { return await Promise.race([operation(controller.signal), expired]); }
  finally { clearTimeout(timer!); }
}

export function requestErrorMessage(error: unknown): string {
  const status = error && typeof error === 'object' && 'status' in error ? Number(error.status) : 0;
  if (status === 401) return 'Сессия завершилась. Войдите в приложение снова.';
  if (status >= 500) return 'Сервер временно недоступен. Повторите загрузку позже.';
  if (error instanceof TypeError) return 'Нет связи с сервером. Проверьте соединение и повторите загрузку.';
  return error instanceof Error ? error.message : 'Не удалось загрузить данные. Повторите запрос.';
}
