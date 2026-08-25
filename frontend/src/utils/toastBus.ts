import type { ToastTone } from '../components/common/Toast';

type Listener = (message: string, tone: ToastTone) => void;

const listeners = new Set<Listener>();

export function onToast(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function emitToast(message: string, tone: ToastTone = 'info'): void {
  listeners.forEach((fn) => fn(message, tone));
}
