import { useEffect, useRef, useState } from 'react';
import { Bell } from 'lucide-react';
import { getNotificationSummary, listNotifications, type NotificationItem } from '../../api/notifications';
import { getDemoRole } from '../auth/LoginScreen';

function NotificationBell() {
  const role = getDemoRole();
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
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
    if (!role || role === 'public') return;
    getNotificationSummary()
      .then((s) => setUnread(s.unread))
      .catch(() => setUnread(0));
  }, [role]);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next) {
      try {
        const data = await listNotifications(1);
        setItems(data.notifications);
        setUnread(data.unread);
      } catch {
        setItems([]);
      }
    }
  };

  if (!role || role === 'public') return null;

  return (
    <div className="notification-bell" ref={rootRef}>
      <button
        type="button"
        className="notification-bell-btn"
        onClick={toggle}
        aria-expanded={open}
        aria-label={unread ? `${unread} unread notifications` : 'Notifications'}
      >
        <Bell size={18} aria-hidden="true" />
        {unread > 0 && <span className="notification-badge">{unread}</span>}
      </button>
      {open && (
        <div className="notification-panel" role="dialog" aria-label="Notifications">
          <h3>Notifications</h3>
          {items.length === 0 ? (
            <p className="notification-empty">No notifications yet.</p>
          ) : (
            <ul>
              {items.map((n) => (
                <li key={n.id}>
                  <strong>{n.subject}</strong>
                  <p>{n.body}</p>
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
