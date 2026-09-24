import { useEffect, useState } from 'react';
import { Bell, Download, FolderOpen, HardDrive, Info, ShieldCheck } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';
import { roleMeta } from '../lib/taskflow';
import { disconnectNotesDirectory, listLocalFolders, listLocalNotes, pickNotesDirectory, storageInfo, type LocalStorageInfo } from '../lib/localNotes';

export function Settings() {
  const { user } = useAuth();
  const roleName = user?.roles?.[0]?.name || 'executor';
  const role = roleMeta[roleName] || roleMeta.executor;
  const [storage, setStorage] = useState<LocalStorageInfo | null>(null);
  const [storageMsg, setStorageMsg] = useState('');

  useEffect(() => {
    storageInfo().then(setStorage).catch(() => {});
  }, []);

  const chooseFolder = async () => {
    setStorageMsg('');
    try {
      const name = await pickNotesDirectory();
      setStorage(await storageInfo());
      setStorageMsg(`Папка подключена: ${name}. Новые личные заметки будут файлами именно там.`);
    } catch (err) {
      setStorageMsg(err instanceof Error ? err.message : 'Не удалось выбрать папку.');
    }
  };

  const dropFolder = async () => {
    await disconnectNotesDirectory();
    setStorage(await storageInfo());
    setStorageMsg('Папка отключена. Личные заметки хранятся во встроенном хранилище браузера на этом ПК.');
  };

  const exportNotes = async () => {
    setStorageMsg('');
    try {
      const [all, folders] = await Promise.all([
        listLocalNotes({}),
        listLocalFolders().catch(() => []),
      ]);
      if (!all.notes.length) {
        setStorageMsg('Локальных заметок пока нет — выгружать нечего.');
        return;
      }
      const folderName = (id: string) => folders.find(f => f.id === id)?.name || 'Без папки';
      const parts = all.notes.map(n => [
        `# ${n.title}`,
        '',
        `- Формат: ${n.format}`,
        `- Папка: ${folderName(n.folderId)}`,
        `- Теги: ${n.tags.join(', ') || '—'}`,
        `- Обновлена: ${n.updated_at}`,
        '',
        '---',
        '',
        n.content || '',
      ].join('\n'));
      const blob = new Blob([parts.join('\n\n')], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `taskflow-notes-${new Date().toISOString().slice(0, 10)}.md`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 5000);
      setStorageMsg(`Выгружено заметок: ${all.notes.length}. Файл сохранён в загрузки.`);
    } catch (err) {
      setStorageMsg(err instanceof Error ? err.message : 'Не удалось выгрузить заметки.');
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h2 className="text-xl font-black">Настройки</h2>
        <p className="text-sm text-[var(--color-text-secondary)]">Профиль, роль и базовая информация по рабочему пространству.</p>
      </div>

      <section className="tf-panel-flat p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-bold"><ShieldCheck size={16} />Профиль</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <InfoRow label="Пользователь" value={user?.username || 'Неизвестно'} />
          <InfoRow label="Роль" value={role.label} />
          <InfoRow label="Права" value={role.hint} wide />
        </div>
      </section>

      <section className="tf-panel-flat p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-bold"><Bell size={16} />Уведомления</h3>
        <p className="text-sm text-[var(--color-text-secondary)]">Внутренние уведомления уже работают: просрочки, события задач и переход к связанному объекту.</p>
      </section>

      <section className="tf-panel-flat p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-bold"><HardDrive size={16} />Личные заметки на этом ПК</h3>
        <p className="text-sm text-[var(--color-text-secondary)]">Личные заметки никогда не отправляются на сервер. Они лежат только здесь: файлами в выбранной папке или во встроенном хранилище браузера. Общие заметки всегда хранятся на сервере.</p>
        <div className="mt-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2.5 text-sm">
          {storage == null ? (
            <span className="text-[var(--color-text-secondary)]">Проверяем хранилище...</span>
          ) : storage.mode === 'dir' ? (
            <span>Папка подключена: <span className="font-semibold text-[var(--color-text)]">{storage.dirName}</span></span>
          ) : (
            <span>Встроенное хранилище браузера{storage.supported ? '' : ' (выбор папки не поддерживается этим браузером)'}</span>
          )}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {storage?.supported !== false && (
            <button type="button" onClick={chooseFolder} className="tf-button"><FolderOpen size={15} />Выбрать папку</button>
          )}
          {storage?.mode === 'dir' && (
            <button type="button" onClick={dropFolder} className="tf-button">Отключить папку</button>
          )}
          <button type="button" onClick={exportNotes} className="tf-button"><Download size={15} />Скачать все (.md)</button>
        </div>
        {storageMsg && <p className="mt-2 text-sm text-[var(--color-text-secondary)]">{storageMsg}</p>}
      </section>

      <section className="tf-panel-flat p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-bold"><Info size={16} />TaskFlow</h3>
        <p className="text-sm text-[var(--color-text-secondary)]">Рабочее пространство для задач, клиентов, календаря, модулей и отчётов команды.</p>
      </section>
    </div>
  );
}

function InfoRow({ label, value, wide }: { label: string; value: string; wide?: boolean }) {
  if (wide) {
    return (
      <div className="md:col-span-2">
        <div className="text-xs text-[var(--color-muted)]">{label}</div>
        <div className="mt-1 text-sm font-semibold">{value}</div>
      </div>
    );
  }
  return (
    <div className="flex items-baseline justify-between gap-4">
      <div className="shrink-0 text-[13px] text-[var(--color-muted)]">{label}</div>
      <div className="min-w-0 truncate text-right text-sm font-semibold">{value}</div>
    </div>
  );
}
