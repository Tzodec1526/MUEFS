import { apiClient } from './client';

export interface FavoriteCase {
  id: number;
  case_id: number;
  case_number: string | null;
  case_title: string | null;
  notes: string | null;
  created_at: string;
}

export async function listFavorites(): Promise<{ favorites: FavoriteCase[]; total: number }> {
  const { data } = await apiClient.get('/favorites');
  return data;
}

export async function addFavorite(caseId: number, notes?: string): Promise<FavoriteCase> {
  const { data } = await apiClient.post('/favorites', { case_id: caseId, notes });
  return data;
}

export async function removeFavorite(caseId: number): Promise<void> {
  await apiClient.delete(`/favorites/${caseId}`);
}

export interface FavoriteCourt {
  id: number;
  court_id: number;
  court_name: string | null;
  county: string | null;
  court_type: string | null;
  notes: string | null;
  created_at: string;
}

export async function listFavoriteCourts(): Promise<{ favorites: FavoriteCourt[]; total: number }> {
  const { data } = await apiClient.get('/favorites/courts');
  return data;
}

export async function addFavoriteCourt(courtId: number, notes?: string): Promise<FavoriteCourt> {
  const { data } = await apiClient.post('/favorites/courts', { court_id: courtId, notes });
  return data;
}

export async function removeFavoriteCourt(courtId: number): Promise<void> {
  await apiClient.delete(`/favorites/courts/${courtId}`);
}
