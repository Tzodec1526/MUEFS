import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { onToast } from '../../utils/toastBus';

export type ToastTone = 'info' | 'success' | 'error';

export interface Toast {
  id: number;
  message: string;
  tone: ToastTone;
}

interface ToastContextValue {
  toasts: Toast[];
  pushToast: (message: string, tone?: ToastTone) => void;
  dismissToast: (id: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let nextId = 1;
const MAX_VISIBLE_TOASTS = 3;
const TOAST_LIFETIME_MS = 5000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const visibleToasts = useRef<Toast[]>([]);
  const timers = useRef(new Map<number, number>());

  const dismissToast = useCallback((id: number) => {
    window.clearTimeout(timers.current.get(id));
    timers.current.delete(id);
    visibleToasts.current = visibleToasts.current.filter(toast => toast.id !== id);
    setToasts(visibleToasts.current);
  }, []);

  const pushToast = useCallback(
    (message: string, tone: ToastTone = 'info') => {
      const duplicate = visibleToasts.current.find(toast => toast.message === message && toast.tone === tone);
      const id = duplicate?.id ?? nextId++;
      if (duplicate) {
        window.clearTimeout(timers.current.get(id));
      } else {
        const next = [...visibleToasts.current, { id, message, tone }];
        if (next.length > MAX_VISIBLE_TOASTS) {
          const removed = next.shift()!;
          window.clearTimeout(timers.current.get(removed.id));
          timers.current.delete(removed.id);
        }
        visibleToasts.current = next;
        setToasts(next);
      }
      timers.current.set(id, window.setTimeout(() => dismissToast(id), TOAST_LIFETIME_MS));
    },
    [dismissToast],
  );

  useEffect(() => onToast(pushToast), [pushToast]);
  useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const timer of pending.values()) window.clearTimeout(timer);
      pending.clear();
    };
  }, []);

  const value = useMemo(
    () => ({ toasts, pushToast, dismissToast }),
    [toasts, pushToast, dismissToast],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-relevant="additions">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`} role="status">
            <span>{t.message}</span>
            <button
              type="button"
              className="toast-dismiss"
              onClick={() => dismissToast(t.id)}
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}
