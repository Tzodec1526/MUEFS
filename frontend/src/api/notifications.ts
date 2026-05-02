import { apiClient } from './client';

export interface Notification {
  id: number;
  type: string;
  subject: string;
  body: string;
  delivery_status: string;
  created_at: string | null;
}

export interface NotificationListResponse {
  notifications: Notification[];
  total: number;
  page: number;
  page_size: number;
}

export async function listNotifications(params?: {
  page?: number;
  page_size?: number;
}): Promise<NotificationListResponse> {
  const { data } = await apiClient.get('/notifications', { params });
  return data;
}
