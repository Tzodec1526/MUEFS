import { useState } from 'react';
import type { ClerkQueueFilters } from '../../api/filings';

const sameFilters = (a: ClerkQueueFilters, b: ClerkQueueFilters) =>
  (a.status || 'all') === (b.status || 'all') && (a.search || '') === (b.search || '')
  && Boolean(a.waiting_48h_only) === Boolean(b.waiting_48h_only);

interface QueueFiltersProps {
  filters: ClerkQueueFilters;
  loading: boolean;
  actionInProgress: boolean;
  onApply: (filters: ClerkQueueFilters) => void;
  onRefresh: () => void;
}

function QueueFilters({ filters, loading, actionInProgress, onApply, onRefresh }: QueueFiltersProps) {
  const [filterDraft, setFilterDraft] = useState(filters);
  const filtersChanged = filterDraft.status !== filters.status || filterDraft.search !== filters.search
    || filterDraft.waiting_48h_only !== filters.waiting_48h_only;
  return (
    <form
      className="queue-filter"
      onSubmit={(e) => {
        e.preventDefault();
        const fields = new FormData(e.currentTarget);
        const submitted: ClerkQueueFilters = {
          status: String(fields.get('status') ?? 'all'),
          search: String(fields.get('search') ?? '').trim(),
          waiting_48h_only: fields.get('waiting_48h_only') !== null,
        };
        if (!sameFilters(submitted, filters)) {
          setFilterDraft(submitted);
          onApply(submitted);
        } else onRefresh();
      }}
    >
      <div className="form-group">
        <label htmlFor="statusFilter">Filter</label>
        <select
          id="statusFilter"
          name="status"
          value={filterDraft.status}
          onChange={(e) => setFilterDraft(previous => ({ ...previous, status: e.target.value }))}
          disabled={actionInProgress}
        >
          <option value="all">All pending</option>
          <option value="submitted">New submissions</option>
          <option value="under_review">Under review</option>
          <option value="waivers">Pending fee waivers</option>
        </select>
      </div>
      <div className="form-group queue-search">
        <label htmlFor="queueSearch">Case title, case number or #filing number</label>
        <input id="queueSearch" name="search" type="search" maxLength={200}
          placeholder="Example: Smith or #123" value={filterDraft.search}
          disabled={actionInProgress}
          onChange={e => setFilterDraft(previous => ({ ...previous, search: e.target.value }))} />
      </div>
      <label className="queue-age-filter">
        <input type="checkbox" name="waiting_48h_only" checked={filterDraft.waiting_48h_only}
          disabled={actionInProgress}
          onChange={e => setFilterDraft(previous => ({ ...previous, waiting_48h_only: e.target.checked }))} />
        Waiting at least 48 hours
      </label>
      <button type="submit" className="btn btn-secondary" disabled={loading || actionInProgress}>
        {loading ? 'Loading...' : filtersChanged ? 'Apply filters' : 'Refresh'}
      </button>
    </form>
  );
}

export default QueueFilters;
