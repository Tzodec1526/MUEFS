import { useEffect, useRef, useState } from 'react';
import { Bell } from 'lucide-react';
import { Link } from 'react-router-dom';
import { listNotifications, type NotificationItem } from '../../api/notifications';
import { getDemoRole } from '../auth/LoginScreen';
import LoadError from '../common/LoadError';

function NotificationBell() {
  const role = getDemoRole();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  useEffect(() => {
    if (!open || !role || role === 'public') return;
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(false);
      try {
        const data = await listNotifications(1);
        if (active) setItems(data.notifications);
      } catch {
        if (active) setError(true);
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => { active = false; };
  }, [open, role, attempt]);

  if (!role || role === 'public') return null;

  return (
    <div className="notification-bell" ref={rootRef}>
      <button
        type="button"
        className="notification-bell-btn"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-label="Notifications"
      >
        <Bell size={18} aria-hidden="true" />
      </button>
      {open && (
        <div className="notification-panel" role="dialog" aria-label="Notifications">
          <h3>Recent notifications</h3>
          {loading ? <p>Loading notifications...</p> : error ? (
            <LoadError message="Could not load notifications." onRetry={() => setAttempt(n => n + 1)} />
          ) : items.length === 0 ? (
            <p className="notification-empty">No notifications yet.</p>
          ) : (
            <ul>
              {items.map((n) => (
                <li key={n.id}>
                  <strong>{n.subject}</strong>
                  <p>{n.body}</p>
                  {n.filing_envelope_id && <Link to={`/filings/${n.filing_envelope_id}/history`} onClick={() => setOpen(false)}>View filing history</Link>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default NotificationBell;
