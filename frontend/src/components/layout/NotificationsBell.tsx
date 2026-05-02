import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listNotifications, Notification } from '../../api/notifications';

interface Props {
  /**
   * Skip mounting the polling query when the user is not signed in / cannot read
   * notifications. Avoids a 401 storm on the login screen.
   */
  enabled: boolean;
}

const POLL_MS = 60_000;
const PAGE_SIZE = 10;

function formatTime(iso: string | null): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function NotificationsBell({ enabled }: Props) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  const { data } = useQuery({
    queryKey: ['notifications', PAGE_SIZE] as const,
    queryFn: () => listNotifications({ page_size: PAGE_SIZE }),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
    enabled,
    staleTime: 15_000,
    retry: false,
  });

  const items: Notification[] = data?.notifications ?? [];
  const total = data?.total ?? 0;

  // Close when a click lands outside the popover.
  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (!wrapperRef.current) return;
      if (!wrapperRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  if (!enabled) return null;

  return (
    <div className="notifications-bell" ref={wrapperRef}>
      <button
        type="button"
        className="notifications-trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
        title={`${total} notification${total === 1 ? '' : 's'}`}
      >
        <span aria-hidden="true">🔔</span>
        {total > 0 && (
          <span className="notifications-badge" aria-label={`${total} notifications`}>
            {total > 99 ? '99+' : total}
          </span>
        )}
        <span className="sr-only">Notifications</span>
      </button>

      {open && (
        <div className="notifications-popover" role="dialog" aria-label="Notifications">
          <div className="notifications-popover-header">
            <strong>Notifications</strong>
            <span>{total} total</span>
          </div>
          {items.length === 0 ? (
            <p className="notifications-empty">No notifications yet.</p>
          ) : (
            <ul className="notifications-list">
              {items.map(n => (
                <li key={n.id} className="notifications-item">
                  <div className="notifications-item-subject">{n.subject}</div>
                  {n.body && <div className="notifications-item-body">{n.body}</div>}
                  <div className="notifications-item-meta">
                    <span>{n.type.replace(/_/g, ' ')}</span>
                    <span>{formatTime(n.created_at)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default NotificationsBell;
