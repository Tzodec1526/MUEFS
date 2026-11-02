import { isDemoBuild } from '../config/demoMode';
import { accessToken, clearSession, oidcSessionExpected } from './keycloak';

export function getDemoRole(): string | null {
  return localStorage.getItem('demo_role');
}

export function hasAdministrationAccess(): boolean {
  return getDemoRole() === 'admin' || localStorage.getItem('administration_access') === 'true';
}

export function hasSession(): boolean {
  return Boolean(accessToken() || (isDemoBuild() && !oidcSessionExpected() && getDemoRole()));
}

export function getDemoCourtId(): number | null {
  const id = localStorage.getItem('demo_court_id');
  return id ? parseInt(id, 10) : null;
}

export function setDemoCourtId(id: number): void {
  localStorage.setItem('demo_court_id', String(id));
}

const DEMO_USER_IDS: Record<string, number> = { attorney: 1, clerk: 2, admin: 3, self_represented: 4, srl: 4, public: 5 };

export function demoUserId(): number | undefined {
  const role = getDemoRole();
  return role ? DEMO_USER_IDS[role] : undefined;
}

export function applyDemoRole(role: string): void {
  clearSession();
  localStorage.setItem('demo_role', role);
  localStorage.setItem('administration_access', String(role === 'admin'));
  if (role === 'clerk') {
    localStorage.setItem('demo_court_id', '3');
  } else {
    localStorage.removeItem('demo_court_id');
  }
}

export type CourtAssignment = { court_id: number; role: string; court_name?: string | null };
export type SessionProfile = {
  user_type: string;
  court_assignments?: CourtAssignment[];
};

const SHELL_ROLE_BY_USER_TYPE: Record<string, string> = {
  attorney: 'attorney',
  clerk: 'clerk',
  judge: 'clerk',
  admin: 'admin',
  self_represented: 'srl',
  public: 'public',
};

export function applySessionFromProfile(profile: SessionProfile): CourtAssignment[] {
  const previousCourt = getDemoCourtId();
  const role = SHELL_ROLE_BY_USER_TYPE[profile.user_type] ?? 'srl';
  localStorage.setItem('demo_role', role);
  localStorage.removeItem('demo_court_id');
  const assignments = profile.court_assignments ?? [];
  localStorage.setItem('administration_access', String(
    role === 'admin' || assignments.some(assignment => assignment.role === 'admin'),
  ));
  const staffCourts = [...new Map(assignments
    .filter(a => ['clerk', 'judge', 'admin'].includes(a.role))
    .map(a => [a.court_id, a])).values()];
  const staff = staffCourts.find(a => a.court_id === previousCourt) ?? staffCourts[0];
  if (staff) {
    localStorage.setItem('demo_court_id', String(staff.court_id));
  }
  return staffCourts;
}
