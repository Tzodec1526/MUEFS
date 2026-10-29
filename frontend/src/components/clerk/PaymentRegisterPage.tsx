import { useContext, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import type { PaymentRegister } from '../../api/payments';
import { formatCents, parseServerDate } from '../../utils/format';
import { getBlobErrorDetail, loadFailure, type LoadFailure } from '../../utils/errors';
import { CourtContext, StaffCourtSelect } from '../auth/CourtSession';
import LoadError from '../common/LoadError';
import { usePageTitle } from '../../utils/pageTitle';

export default function PaymentRegisterPage() {
  const { court, courts } = useContext(CourtContext)!;
  usePageTitle('Receipt register', court?.court_name);
  const courtId = court!.court_id;
  const administrator = courts.some(item => item.court_id === courtId && item.role === 'admin');
  const [filters, setFilters] = useState(() => {
    const today = new Date();
    const date = [today.getFullYear(), String(today.getMonth() + 1).padStart(2, '0'), String(today.getDate()).padStart(2, '0')].join('-');
    return { date_from: date, date_to: date, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, include_simulated: false };
  });
  const [dirty, setDirty] = useState(false);
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: PaymentRegister; error?: LoadFailure }>();
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const exportRequest = useRef<AbortController | null>(null);
  const key = JSON.stringify([courtId, filters, page, attempt]);
  const current = result?.key === key ? result : undefined;
  const report = current?.data;
  useEffect(() => {
    if (!administrator) return;
    const controller = new AbortController();
    apiClient.get<PaymentRegister>('/clerk/payment-register', {
      params: { court_id: courtId, ...filters, page }, signal: controller.signal,
    }).then(({ data }) => { if (!controller.signal.aborted) setResult({ key, data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not load the receipt register.') }); });
    return () => controller.abort();
  }, [courtId, administrator, filters, page, key]);
  useEffect(() => () => exportRequest.current?.abort(), []);

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const zoneInput = event.currentTarget.elements.namedItem('timezone') as HTMLInputElement;
    try { new Intl.DateTimeFormat(undefined, { timeZone: zoneInput.value }); }
    catch {
      zoneInput.setCustomValidity('Choose a time zone supported by this browser.');
      zoneInput.reportValidity();
      return;
    }
    setFilters({ date_from: String(data.get('date_from')), date_to: String(data.get('date_to')),
      timezone: String(data.get('timezone')), include_simulated: data.has('include_simulated') });
    setPage(1); setAttempt(n => n + 1); setDirty(false); setExportError('');
  }

  async function exportCsv() {
    const controller = new AbortController();
    exportRequest.current = controller;
    setExporting(true); setExportError('');
    try {
      const { data } = await apiClient.get<Blob>('/clerk/payment-register', {
        params: { court_id: courtId, ...filters, format: 'csv' },
        responseType: 'blob', signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(data);
      const link = document.createElement('a');
      link.href = url;
      link.download = `court-${courtId}-receipts-${filters.date_from}-${filters.date_to}.csv`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      if (controller.signal.aborted) return;
      const detail = await getBlobErrorDetail(err);
      if (!controller.signal.aborted) setExportError(detail || 'Could not export the receipt register.');
    } finally { if (!controller.signal.aborted) setExporting(false); }
  }

  return <section className="payment-register">
    <StaffCourtSelect disabled={exporting} />
    <div className="page-header"><h2>External receipt register</h2>
      <Link to="/clerk/fee-reviews" className="btn btn-secondary">Fee reviews</Link></div>
    {!administrator ? <p className="alert alert-warning">An administrator assignment to this court is required to view its receipt register.</p> : <>
      <p>Reconcile credits and reversals by the date the portal recorded them. Compare these entries with the court’s external receipt records.</p>
      <form className="review-card" onSubmit={apply} onChange={() => setDirty(true)}>
        <fieldset disabled={exporting}>
          <legend>Recorded activity period</legend>
          <div className="calendar-range">
            <div className="form-group"><label htmlFor="register-from">From date</label>
              <input id="register-from" name="date_from" type="date" defaultValue={filters.date_from} required /></div>
            <div className="form-group"><label htmlFor="register-to">Through date</label>
              <input id="register-to" name="date_to" type="date" defaultValue={filters.date_to} required /></div>
            <div className="form-group"><label htmlFor="register-zone">Time zone</label>
              <input id="register-zone" name="timezone" defaultValue={filters.timezone} maxLength={100} required list="register-zones"
                onInput={event => event.currentTarget.setCustomValidity('')} />
              <datalist id="register-zones"><option value="America/Detroit" /><option value="America/Menominee" /><option value="UTC" /></datalist></div>
          </div>
          <p className="info-text">Choose up to 31 days, inclusive. The initial time zone comes from your device.</p>
          <label className="checkbox-label"><input name="include_simulated" type="checkbox" defaultChecked={filters.include_simulated} /> Include simulated activity, with separate totals</label>
          <button className="btn btn-primary" type="submit">Apply period</button>
          {dirty && <p role="status">Apply your changes to update the register and export.</p>}
        </fieldset>
      </form>
      {!current && <p role="status">Loading receipt activity…</p>}
      {current?.error && <LoadError failure={current.error} onRetry={() => setAttempt(n => n + 1)} />}
      {report && <>
        <h3>{report.date_from} through {report.date_to} · {report.timezone}</h3>
        <p>{report.total} recorded {report.total === 1 ? 'entry' : 'entries'} · Generated {parseServerDate(report.generated_at).toLocaleString(undefined, { timeZone: report.timezone })} ({report.timezone})</p>
        <dl className="register-totals">
          <div><dt>External credits</dt><dd>{formatCents(report.totals.credits_cents)}</dd></div>
          <div><dt>Reversals</dt><dd>{formatCents(report.totals.reversals_cents)}</dd></div>
          <div><dt>Net recorded activity</dt><dd>{formatCents(report.totals.credits_cents - report.totals.reversals_cents)}</dd></div>
        </dl>
        {report.include_simulated && <p className="alert alert-warning">Simulated activity only: credits {formatCents(report.simulated_totals.credits_cents)}, reversals {formatCents(report.simulated_totals.reversals_cents)}, net {formatCents(report.simulated_totals.credits_cents - report.simulated_totals.reversals_cents)}. Excluded from the totals above.</p>}
        <button className="btn btn-secondary" disabled={dirty || exporting || !report.total || report.total > 5000}
          onClick={() => void exportCsv()}>{exporting ? 'Exporting…' : 'Export applied period as CSV'}</button>
        <p className="info-text">Exports use a fresh read of the applied period, up to 5,000 entries. Choose a shorter period for larger registers. CSV formula-like text is prefixed with an apostrophe; original text remains in the private filing history.</p>
        {exportError && <p className="alert alert-error" role="alert">{exportError}</p>}
        {!report.total && <p className="empty-state">No external receipt activity was recorded in this period.</p>}
        <ol className="payment-record-list">{report.entries.map(entry => <li key={entry.event_id}>
          <div className="page-header"><strong>{entry.event_type === 'fee_payment_reversed' ? 'Credit reversed' : 'Receipt credited'} · {formatCents(entry.amount_cents)}</strong>
            {entry.is_simulated && <span>Simulated</span>}</div>
          <p><Link to={`/filings/${entry.filing_id}/fees`}>Filing #{entry.filing_id}</Link> · Payment #{entry.payment_id}</p>
          <p>{entry.receipt_system} · Receipt {entry.receipt_reference}</p>
          <p>Recorded {parseServerDate(entry.occurred_at).toLocaleString(undefined, { timeZone: report.timezone })} ({report.timezone}) by {entry.actor_name}</p>
          <p>Source received {parseServerDate(entry.received_at).toLocaleString(undefined, { timeZone: report.timezone })}</p>
          <details><summary>Reason and retained event</summary><p>{entry.reason}</p><p>Event {entry.event_id}</p>
            <Link to={`/filings/${entry.filing_id}/history`}>View filing history</Link></details>
        </li>)}</ol>
        {report.total > 50 && <nav className="pagination" aria-label="Receipt register pages">
          <button className="btn btn-secondary" disabled={page === 1 || dirty || exporting} onClick={() => setPage(n => n - 1)}>Previous</button>
          <span>Page {page} of {Math.ceil(report.total / 50)}</span>
          <button className="btn btn-secondary" disabled={page * 50 >= report.total || dirty || exporting} onClick={() => setPage(n => n + 1)}>Next</button>
        </nav>}
      </>}
    </>}
  </section>;
}
