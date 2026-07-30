import { Bell, Info, ShieldCheck } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';
import { roleMeta } from '../lib/taskflow';

export function Settings() {
  const { user } = useAuth();
  const roleName = user?.roles?.[0]?.name || 'executor';
  const role = roleMeta[roleName] || roleMeta.executor;

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
        <h3 className="mb-3 flex items-center gap-2 text-sm font-bold"><Info size={16} />TaskFlow</h3>
        <p className="text-sm text-[var(--color-text-secondary)]">Рабочее пространство для задач, клиентов, календаря, модулей и отчётов команды.</p>
      </section>
    </div>
  );
}

function InfoRow({ label, value, wide }: { label: string; value: string; wide?: boolean }) {
  return (
    <div className={wide ? 'md:col-span-2' : ''}>
      <div className="text-xs text-[var(--color-muted)]">{label}</div>
      <div className="mt-1 text-sm font-semibold">{value}</div>
    </div>
  );
}
