import { useEffect, useId, useRef, useState } from 'react';
import { Bell } from 'lucide-react';
import { Link } from 'react-router-dom';
import { deliveryLabels, listNotifications, type NotificationItem } from '../../api/notifications';
import { getDemoRole } from '../auth/LoginScreen';
import LoadError from '../common/LoadError';
import { loadFailure, type LoadFailure } from '../../utils/errors';

function NotificationBell() {
  const role = getDemoRole();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<LoadFailure | null>(null);
  const [attempt, setAttempt] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  // A disclosure: it closes on Escape (returning focus to its button), on a click outside,
  // and when keyboard focus moves outside it (see onBlur below).
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setOpen(false);
      toggleRef.current?.focus();
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (!open || !role || role === 'public') return;
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await listNotifications(1);
        if (active) setItems(data.notifications);
      } catch (err) {
        if (active) setError(loadFailure(err, 'Could not load notifications.'));
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => { active = false; };
  }, [open, role, attempt]);

  if (!role || role === 'public') return null;

  return (
    <div
      className="notification-bell"
      ref={rootRef}
      onBlur={(event) => {
        // Focus that moves to another control outside closes the panel; a click on the panel's
        // own text (no new focus target) does not.
        const next = event.relatedTarget as Node | null;
        if (open && next && !event.currentTarget.contains(next)) setOpen(false);
      }}
    >
      <button
        ref={toggleRef}
        type="button"
        className="notification-bell-btn"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        aria-label="Notifications"
      >
        <Bell size={18} aria-hidden="true" />
      </button>
      {open && (
        <div className="notification-panel" id={panelId}>
          <h3>Recent notifications</h3>
          {loading ? <p>Loading notifications...</p> : error ? (
            <LoadError failure={error} onRetry={() => setAttempt(n => n + 1)} />
          ) : items.length === 0 ? (
            <p className="notification-empty">No notifications yet.</p>
          ) : (
            <ul>
              {items.map((n) => (
                <li key={n.id}>
                  <strong>{n.subject}</strong>
                  <p>{n.body}</p>
                  <p>{deliveryLabels[n.delivery_status] || n.delivery_status}</p>
                  {n.filing_envelope_id && <Link to={`/filings/${n.filing_envelope_id}/history`} onClick={() => setOpen(false)}>View filing history</Link>}
                </li>
              ))}
            </ul>
          )}
          <Link to="/notifications" onClick={() => setOpen(false)}>All notices &amp; email status</Link>
        </div>
      )}
    </div>
  );
}

export default NotificationBell;
