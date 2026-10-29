import { useEffect, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { getCourt } from '../../api/courts';
import type { FilingDateAssessment } from '../../api/filings';
import { formatCourtDate, parseServerDate } from '../../utils/format';
import { errorMessage, loadFailure, type LoadFailure } from '../../utils/errors';
import LoadError from '../common/LoadError';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

interface Calendar {
  id: number; timezone: string; valid_from: string; valid_through: string;
  closed_dates: Record<string, string>; authority_reference: string; published_at: string;
}
interface CalendarList { calendars: Calendar[]; total: number; can_publish: boolean }

export default function CourtCalendarPage() {
  const { courtId } = useParams();
  const [data, setData] = useState<CalendarList>();
  const [courtName, setCourtName] = useState('Court');
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<LoadFailure | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [assessment, setAssessment] = useState<FilingDateAssessment>();
  usePageTitle('Filing calendar', data ? courtName : undefined);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true); setError(null);
      try {
        const [court, response] = await Promise.all([
          getCourt(Number(courtId)),
          apiClient.get<CalendarList>(`/courts/${courtId}/calendars`, { params: { page }, signal: controller.signal }),
        ]);
        if (!controller.signal.aborted) { setCourtName(court.name); setData(response.data); }
      } catch (err) {
        if (!controller.signal.aborted) setError(loadFailure(err, 'Could not load court calendars.'));
      } finally { if (!controller.signal.aborted) setLoading(false); }
    }
    load();
    return () => controller.abort();
  }, [courtId, page, attempt]);

  async function publish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const closedDates: Record<string, string> = {};
    setActionError(null); setMessage('');
    for (const line of String(values.get('closures') || '').split('\n').filter(line => line.trim())) {
      const match = /^(\d{4}-\d{2}-\d{2})\s+(.+)$/.exec(line.trim());
      if (!match || closedDates[match[1]]) {
        setActionError('Use one unique date and reason per line: YYYY-MM-DD Holiday or closure reason');
        return;
      }
      closedDates[match[1]] = match[2];
    }
    setBusy(true);
    try {
      await apiClient.post(`/courts/${courtId}/calendars`, {
        timezone: values.get('timezone'), valid_from: values.get('valid_from'),
        valid_through: values.get('valid_through'), closed_dates: closedDates,
        authority_reference: values.get('authority_reference'),
      });
      form.reset(); setPage(1); setAttempt(n => n + 1);
      setAssessment(undefined); setMessage('Calendar revision published. Earlier revisions and receipts are retained.');
    } catch (err) { setActionError(errorMessage(err, 'Could not publish the calendar.')); }
    finally { setBusy(false); }
  }

  async function preview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setBusy(true); setActionError(null); setAssessment(undefined);
    try {
      const response = await apiClient.get<FilingDateAssessment>(`/courts/${courtId}/filing-date`, {
        params: { received_at: values.get('received_at') },
      });
      setAssessment(response.data);
    } catch (err) { setActionError(errorMessage(err, 'Could not assess this receipt timestamp.')); }
    finally { setBusy(false); }
  }

  return <section className="court-calendar-page">
    <div className="page-header"><div><PageHeading>{courtName}: filing calendar</PageHeading>
      <p>Published timezones, legal holidays and court-ordered closures.</p></div>
      <Link className="btn btn-secondary" to={`/courts/${courtId}/intake`}>Electronic intake status</Link></div>
    <p>Electronic submissions can arrive at any time. Under MCR 1.109(G)(5)(b), weekend and closed-day
      submissions are assigned to the next business day. This calendar does not calculate deadlines or decide requests for relief.</p>
    {loading && <p role="status">Loading calendars…</p>}
    {error && <LoadError failure={error} onRetry={() => setAttempt(n => n + 1)} />}
    {message && <p className="alert alert-success" role="status">{message}</p>}
    {actionError && <p className="alert alert-error" role="alert">{actionError}</p>}
    {!loading && !error && data && <>
      {data.can_publish && <details className="review-card">
        <summary>Publish a reviewed calendar revision</summary>
        <form onSubmit={publish}>
          <p>Newer revisions replace overlapping dates for future assessments. All unlisted weekdays are
            treated as open. Include every applicable legal holiday and court-ordered closure.</p>
          <div className="form-group"><label htmlFor="calendar-timezone">Court timezone</label>
            <input id="calendar-timezone" name="timezone" placeholder="America/Detroit" maxLength={64} required /></div>
          <div className="calendar-range">
            <div className="form-group"><label htmlFor="calendar-from">Coverage starts</label>
              <input id="calendar-from" type="date" name="valid_from" required /></div>
            <div className="form-group"><label htmlFor="calendar-through">Coverage ends</label>
              <input id="calendar-through" type="date" name="valid_through" required /></div>
          </div>
          <div className="form-group"><label htmlFor="calendar-closures">Holidays and court-ordered closures</label>
            <textarea id="calendar-closures" name="closures" rows={6}
              placeholder="2026-09-07 Labor Day" aria-describedby="closure-format" /></div>
          <p id="closure-format">One date and reason per line. Weekends are already excluded. Cover the next business day
            after year-end, either here or in another published calendar.</p>
          <div className="form-group"><label htmlFor="calendar-authority">Approving authority or source</label>
            <textarea id="calendar-authority" name="authority_reference" rows={2} maxLength={1000} required /></div>
          <button className="btn btn-primary" disabled={busy}>{busy ? 'Publishing…' : 'Publish calendar revision'}</button>
        </form>
      </details>}
      <form className="review-card" onSubmit={preview}>
        <h3>Check a receipt timestamp</h3>
        <div className="form-group"><label htmlFor="calendar-received">Received timestamp, including UTC offset</label>
          <input id="calendar-received" name="received_at" placeholder="2026-09-05T03:59:00Z" required /></div>
        <button className="btn btn-secondary" disabled={busy}>Check filing date</button>
        {assessment && <div className="calendar-assessment" role="status">
          <p>Filing date: <strong>{formatCourtDate(assessment.filing_date)}</strong></p>
          {assessment.error && <p className="alert alert-warning">{assessment.error}</p>}
          {assessment.timezone && <p>Local receipt date: {formatCourtDate(assessment.local_received_date)} · {assessment.timezone}</p>}
          {Object.entries(assessment.skipped_dates).map(([day, reason]) => <p key={day}>{formatCourtDate(day)}: {reason}</p>)}
          {assessment.calendar_ids.length > 0 && <p>Calendar revisions: {assessment.calendar_ids.join(', ')}</p>}
        </div>}
      </form>
      {data.calendars.length === 0 && <p className="alert alert-warning">No calendar has been published. Filing dates cannot be established from a calendar yet.</p>}
      {data.calendars.map(calendar => <article className="review-card" key={calendar.id}>
        <h3>Calendar revision #{calendar.id}</h3>
        <p>{formatCourtDate(calendar.valid_from)} – {formatCourtDate(calendar.valid_through)} · {calendar.timezone}</p>
        <p>Authority: {calendar.authority_reference}</p>
        <p>Published: {parseServerDate(calendar.published_at).toISOString().replace('T', ' ').replace('Z', ' UTC')}</p>
        <ul>{Object.entries(calendar.closed_dates).sort(([a], [b]) => a.localeCompare(b)).map(([day, reason]) =>
          <li key={day}>{formatCourtDate(day)} — {reason}</li>)}</ul>
        {Object.keys(calendar.closed_dates).length === 0 && <p>No additional closed dates in this revision. Weekends remain excluded.</p>}
      </article>)}
      {data.total > 25 && <nav className="pagination" aria-label="Calendar revisions">
        <button className="btn btn-secondary" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</button>
        <span>Page {page} of {Math.ceil(data.total / 25)}</span>
        <button className="btn btn-secondary" disabled={page * 25 >= data.total} onClick={() => setPage(p => p + 1)}>Next</button>
      </nav>}
    </>}
  </section>;
}
