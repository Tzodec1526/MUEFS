import { apiClient } from './client';

export interface NotificationItem {
  id: number;
  type: string;
  subject: string;
  body: string;
  delivery_status: string;
  created_at: string | null;
}
export async function listNotifications(page = 1): Promise<{
  notifications: NotificationItem[];
  total: number;
}> {
  const { data } = await apiClient.get('/notifications', { params: { page } });
  return data;
}
