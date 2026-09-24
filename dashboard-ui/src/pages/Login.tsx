import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';

const APPLE_FONT = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', Inter, 'Segoe UI', sans-serif";

export function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await login(username, password);
      navigate('/');
    } catch {
      setError('Неверное имя или пароль');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="anim-page grid min-h-screen place-items-center px-4" style={{ fontFamily: APPLE_FONT }}>
      <div
        aria-hidden
        className="pointer-events-none fixed left-1/2 top-[-12rem] h-[28rem] w-[46rem] -translate-x-1/2 rounded-full"
        style={{ background: 'radial-gradient(closest-side, rgba(120,100,70,.16), transparent)' }}
      />
      <div className="relative w-full max-w-[400px]">
        <div className="mb-10 text-center">
          <div className="mx-auto grid h-16 w-16 place-items-center rounded-[20px] text-[22px] font-semibold text-[var(--color-on-accent)]" style={{ background: 'var(--color-accent)', boxShadow: 'var(--shadow-accent)' }}>
            TF
          </div>
          <h1 className="mt-6 text-[32px] font-semibold tracking-tight text-[var(--color-text)]">TaskFlow</h1>
          <p className="mt-2 text-[15px] text-[var(--color-text-secondary)]">SEO / dev workspace команды</p>
        </div>
        <form
          onSubmit={handleSubmit}
          className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-surface)] p-7"
          style={{ boxShadow: 'var(--shadow-panel)' }}
        >
          <div className="space-y-4">
            <label className="block">
              <span className="mb-2 block text-[13px] font-medium text-[var(--color-text-secondary)]">Логин</span>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                autoFocus
                className="tf-input h-12 rounded-2xl text-[15px]"
                placeholder="Имя пользователя"
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-[13px] font-medium text-[var(--color-text-secondary)]">Пароль</span>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="tf-input h-12 rounded-2xl text-[15px]"
                placeholder="••••••••"
              />
            </label>
          </div>
          {error && <p className="mt-4 text-center text-[14px] font-medium text-[var(--color-danger)]">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="tf-button-primary mt-6 inline-flex h-12 w-full items-center justify-center gap-2 rounded-full text-[16px]"
          >
            {loading ? 'Вход...' : (<>Войти <ArrowRight size={17} /></>)}
          </button>
        </form>
        <p className="mt-8 text-center text-[13px] text-[var(--color-muted)]">Внутренняя система команды</p>
      </div>
    </div>
  );
}
