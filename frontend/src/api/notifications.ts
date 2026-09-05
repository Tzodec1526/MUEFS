import { apiClient } from './client';

export interface NotificationItem {
  id: number;
  filing_envelope_id: number | null;
  type: string;
  subject: string;
  body: string;
  delivery_status: string;
  created_at: string | null;
  email_recipient: string | null;
  attempt_count: number;
  last_error: string | null;
  sent_at: string | null;
  next_attempt_at: string | null;
}
export const deliveryLabels: Record<string, string> = {
  disabled: 'Portal only', blocked: 'Recipient verification needed', pending: 'Email queued',
  sending: 'Email sending', sent: 'Accepted by email relay', failed: 'Email failed',
  unknown: 'Email outcome unknown', legacy: 'Historical status (unverified)',
};

export async function listNotifications(page = 1, filters: {
  court_id?: number; delivery_status?: string;
} = {}, signal?: AbortSignal): Promise<{
  notifications: NotificationItem[];
  total: number;
  page_size: number;
  email_enabled: boolean;
}> {
  const { data } = await apiClient.get('/notifications', { params: { page, ...filters }, signal });
  return data;
}
