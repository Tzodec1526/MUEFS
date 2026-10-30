import { createContext, Fragment, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { apiClient } from '../../api/client';
import { loadFailure, type LoadFailure } from '../../utils/errors';
import PageLoadError from '../common/PageLoadError';
import {
  applySessionFromProfile, getDemoCourtId, getDemoRole, hasSession, setDemoCourtId,
  type CourtAssignment, type SessionProfile,
} from '../../auth/session';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

interface CourtSessionState {
  userId?: number;
  role: string | null;
  courts: CourtAssignment[];
  court: CourtAssignment | undefined;
  loading: boolean;
  error?: LoadFailure;
  selectCourt: (id: number) => void;
  refresh: () => void;
}

export const CourtContext = createContext<CourtSessionState | null>(null);

export function CourtSession({ children }: { children: ReactNode }) {
  const signedIn = hasSession();
  const [attempt, setAttempt] = useState(0);
  const [selectedId, setSelectedId] = useState(getDemoCourtId);
  const [result, setResult] = useState<{ attempt: number; userId?: number; courts: CourtAssignment[]; error?: LoadFailure }>();
  const current = result?.attempt === attempt ? result : undefined;
  const courts = signedIn ? current?.courts ?? [] : [];
  const court = courts.find(item => item.court_id === selectedId) ?? courts[0];

  useEffect(() => {
    if (!signedIn) return;
    const controller = new AbortController();
    apiClient.get<SessionProfile & { id: number }>('/auth/me', { signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      const courts = applySessionFromProfile(data);
      setSelectedId(getDemoCourtId());
      setResult({ attempt, userId: data.id, courts });
    }).catch(err => {
      if (!controller.signal.aborted) setResult({ attempt, courts: [], error: loadFailure(err, 'Could not verify court assignments.') });
    });
    return () => controller.abort();
  }, [signedIn, attempt]);

  function selectCourt(id: number) {
    if (!courts.some(item => item.court_id === id)) return;
    setDemoCourtId(id);
    setSelectedId(id);
  }

  return <CourtContext.Provider value={{ userId: signedIn ? current?.userId : undefined, role: getDemoRole(), courts, court, loading: signedIn && !current,
    error: current?.error, selectCourt, refresh: () => setAttempt(n => n + 1) }}>
    {children}
  </CourtContext.Provider>;
}

function CourtAssignmentNeeded({ refresh }: { refresh: () => void }) {
  usePageTitle('Court assignment needed');
  return <div className="empty-state">
    <PageHeading>Court assignment needed</PageHeading>
    <p>A clerk, judge or administrator assignment is required to use this court workspace.</p>
    <button className="btn btn-secondary" onClick={refresh}>Refresh assignments</button>
  </div>;
}

function CourtWorkspaceLoading() {
  usePageTitle('Loading court workspace');
  return <>
    <h1>Loading court workspace</h1>
    <p role="status">Loading court assignments…</p>
  </>;
}

function CourtWorkspaceUnavailable({ failure, onRetry }: { failure: LoadFailure; onRetry: () => void }) {
  usePageTitle('Court workspace not loaded');
  return <PageLoadError heading="Court workspace not loaded" failure={failure} onRetry={onRetry} />;
}

export function CourtWorkspace({ children }: { children: ReactNode }) {
  const { court, loading, error, refresh } = useContext(CourtContext)!;
  if (loading) return <CourtWorkspaceLoading />;
  if (error) return <CourtWorkspaceUnavailable failure={error} onRetry={refresh} />;
  if (!court) return <CourtAssignmentNeeded refresh={refresh} />;
  // Changing courts discards selections, pagination and pending reads from the prior court.
  return <Fragment key={court.court_id}>{children}</Fragment>;
}

// Set when the focused working-court select changes courts. CourtWorkspace then remounts the
// page for the new court, replacing the select, and the replacement takes focus back.
let refocusCourtSelect = false;

export function StaffCourtSelect({ disabled = false, onChange }: { disabled?: boolean; onChange?: () => void }) {
  const { court, courts, selectCourt, refresh } = useContext(CourtContext)!;
  const select = useRef<HTMLSelectElement>(null);
  const courtId = court?.court_id;
  // Runs in the commit that applies the change, for a replacement or for this same select.
  useLayoutEffect(() => {
    if (!refocusCourtSelect) return;
    refocusCourtSelect = false;
    select.current?.focus();
  }, [courtId]);
  return <div className="staff-court-select">
    <div className="form-group"><label htmlFor="working-court">Working court</label>
      <select id="working-court" ref={select} value={court?.court_id ?? ''} disabled={disabled || !court}
        onChange={event => {
          const id = Number(event.target.value);
          refocusCourtSelect = document.activeElement === event.currentTarget
            && id !== courtId && courts.some(item => item.court_id === id);
          selectCourt(id);
          onChange?.();
        }}>
        {courts.map(item => <option key={item.court_id} value={item.court_id}>{item.court_name || `Court ${item.court_id}`}</option>)}
      </select></div>
    <button type="button" className="btn btn-secondary" disabled={disabled} onClick={refresh}>Refresh assignments</button>
    {disabled && <p>Close the open review and wait for any action to finish before changing courts.</p>}
  </div>;
}
