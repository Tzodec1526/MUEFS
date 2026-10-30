import { useCallback, useEffect, useRef, useState } from 'react';
import { getClerkQueue, type ClerkQueue, type ClerkQueueFilters } from '../../api/filings';
import { loadFailure, type LoadFailure } from '../../utils/errors';

export const focusQueueRow = (filingId: number) =>
  document.getElementById(`queue-filing-${filingId}`)?.querySelector('button')?.focus();

export function useClerkQueue(courtId: number, autoRefreshPaused: boolean) {
  const [queue, setQueue] = useState<ClerkQueue | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedSubmissions, setSelectedSubmissions] = useState<Map<number, number>>(() => new Map());
  const [filters, setFilters] = useState<ClerkQueueFilters>({ status: 'all', search: '', waiting_48h_only: false });
  const [page, setPage] = useState(1);
  const requestRef = useRef<AbortController | null>(null);
  const [queueError, setQueueError] = useState<LoadFailure | null>(null);

  const fetchQueue = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setLoading(true);
    setQueueError(null);
    try {
      const result = await getClerkQueue(courtId, { ...filters, page, signal: controller.signal });
      if (controller.signal.aborted) return;
      if (page > 1 && result.filings.length === 0) {
        setPage(Math.max(1, Math.ceil(result.total / result.page_size)));
        return;
      }
      setQueue(result);
      setSelectedSubmissions(previous => new Map(result.filings
        .filter(filing => previous.get(filing.id) === filing.submission_count)
        .map(filing => [filing.id, filing.submission_count])));
    } catch (err) {
      if (controller.signal.aborted) return;
      setQueueError(loadFailure(err, "We couldn't load the review queue. Please retry."));
      setQueue(null);
      setSelectedSubmissions(new Map());
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [courtId, page, filters]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- existing pattern; fetchQueue performs the setState for loading/data
    fetchQueue();
    return () => requestRef.current?.abort();
  }, [fetchQueue]);

  useEffect(() => {
    const interval = setInterval(() => {
      if (!document.hidden && !autoRefreshPaused) fetchQueue();
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchQueue, autoRefreshPaused]);

  return {
    queue, loading, setLoading, queueError, filters, setFilters, page, setPage,
    selectedSubmissions, setSelectedSubmissions, fetchQueue,
  };
}
