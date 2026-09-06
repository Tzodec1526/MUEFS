import { useEffect, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiClient } from '../../api/client';
import type { FilingDateBasis } from '../../api/filings';
import { getErrorDetail } from '../../utils/errors';
import { formatCourtDate, parseServerDate } from '../../utils/format';
import FilingDateEvidence from '../filing/FilingDateEvidence';
import LoadError from '../common/LoadError';

interface DateState {
  filing_id: number; court_id: number; status: string; submission_count: number;
  submitted_at: string | null; filing_date: string | null; filing_date_basis: FilingDateBasis | null;
  version: number; case_id: number | null; case_number: string | null;
  case_filing_date: string | null; case_date_version: number | null; order_block: string | null;
}

export default function FilingDateOrderPage() {
  const { filingId } = useParams();
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: DateState; error?: string }>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [receipt, setReceipt] = useState('');
  const key = `${filingId}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  const data = current?.data;
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<DateState>(`/clerk/filings/${filingId}/filing-date`, { signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setResult({ key, data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: getErrorDetail(err) || 'Could not load filing dates.' }); });
    return () => controller.abort();
  }, [filingId, key]);

  async function record(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!data || busy) return;
    const form = new FormData(event.currentTarget);
    form.set('expected_version', String(data.version));
    if (data.case_date_version !== null) form.set('expected_case_version', String(data.case_date_version));
    setBusy(true); setError(''); setReceipt('');
    try {
      const response = await apiClient.post<{ transaction_id: string }>(`/clerk/filings/${filingId}/filing-date`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setReceipt(response.data.transaction_id);
      setAttempt(n => n + 1);
    } catch (err) {
      setError(getErrorDetail(err) || 'Could not confirm the decision. Check filing history before trying again.');
    } finally {
      setBusy(false);
    }
  }

  return <section className="filing-date-page">
    <div className="page-header">
      <div><h2>Filing #{filingId}: record a filing-date order</h2>
        <p>Enter the date established by an existing signed court order.</p></div>
      <Link className="btn btn-secondary" to={`/filings/${filingId}/history`}>Receipts &amp; history</Link>
    </div>
    {receipt && <div className="alert alert-success" role="status">Court-ordered filing date recorded. Transaction <code>{receipt}</code>.</div>}
    {error && <p className="alert alert-error" role="alert">{error}</p>}
    {!current && <p role="status">Loading filing dates…</p>}
    {current?.error && <LoadError message={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {data && <>
      <div className="review-card">
        <h3>Current record</h3>
        <p>Submission {data.submission_count || 'not recorded'} · {data.status.replace(/_/g, ' ')}</p>
        <p>Receipt time: {data.submitted_at ? parseServerDate(data.submitted_at).toISOString().replace('T', ' ').replace('Z', ' UTC') : 'Not recorded'}</p>
        <p>Filing date: <strong>{formatCourtDate(data.filing_date)}</strong></p>
        {data.filing_date_basis && <FilingDateEvidence basis={data.filing_date_basis} />}
        {data.case_id && <p>Case {data.case_number}: opening date <strong>{formatCourtDate(data.case_filing_date)}</strong></p>}
        <button className="btn btn-secondary btn-small" disabled={busy} onClick={() => { setError(''); setAttempt(n => n + 1); }}>Refresh dates</button>
      </div>
      {data.order_block ? <p className="alert alert-warning">{data.order_block}</p> : <form className="review-card" key={key} onSubmit={record}>
        <h3>Signed court order</h3>
        <p>Record the date exactly as ordered. This decision applies to the current submission and preserves its receipt time and status.
          A later corrected submission requires its own date review.</p>
        <fieldset disabled={busy}>
          <div className="form-group"><label htmlFor="ordered-date">Filing date established by the order</label>
            <input id="ordered-date" name="filing_date" type="date" required /></div>
          <div className="form-group"><label htmlFor="signed-date">Date the order was signed</label>
            <input id="signed-date" name="order_signed_date" type="date" required /></div>
          <div className="form-group"><label htmlFor="order-reference">Order reference</label>
            <input id="order-reference" name="authority_reference" maxLength={1000} required placeholder="Judge and docket/order reference" /></div>
          <div className="form-group"><label htmlFor="order-reason">Reason recorded in the order</label>
            <textarea id="order-reason" name="reason" maxLength={5000} required rows={3} /></div>
          <div className="form-group"><label htmlFor="signed-order">Signed order (PDF)</label>
            <input id="signed-order" name="file" type="file" accept="application/pdf,.pdf" required /></div>
          <p>The retained signed PDF is available to the filer and court staff. Use Manage public access in the receipt to publish a reviewed public copy.</p>
          {data.case_id ? <label className="checkbox-label"><input name="update_case_date" type="checkbox" value="true" />
            Apply this date to the opening date of case {data.case_number}, as directed by the same order.</label>
            : <p>If acceptance creates a new case, its opening date will use this filing date.</p>}
          <label className="checkbox-label"><input name="reviewed" type="checkbox" value="true" required />
            I reviewed the signed order and confirm that the entered date and any case opening date change are authorized by it.</label>
          <button className="btn btn-primary" type="submit">{busy ? 'Recording order…' : 'Record court-ordered date'}</button>
        </fieldset>
      </form>}
    </>}
  </section>;
}
