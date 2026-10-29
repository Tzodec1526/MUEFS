import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getFilingHistory, type FilingHistory, type FilingTransaction } from '../../api/filings';
import { getDemoRole } from '../auth/LoginScreen';
import DocumentDownload from '../common/DocumentDownload';
import LoadError from '../common/LoadError';
import { loadFailure, type LoadFailure } from '../../utils/errors';
import FeeWaiverPanel, { waiverActionLabels } from './FeeWaiverPanel';
import FilingDateEvidence from './FilingDateEvidence';
import { formatBytes, formatCents, formatCourtDate, getDocumentLabel, parseServerDate } from '../../utils/format';

const eventLabels: Record<string, string> = {
  submitted: 'Submission received', accepted: 'Accepted by the court',
  returned: 'Returned for correction', rejected: 'Rejected',
  cms_failed: 'Court system submission failed', service_recorded: 'Service-only documents recorded',
  waiver_referred: 'Fee waiver referred for judicial review', waiver_granted: 'Fee waiver granted',
  waiver_denied: 'Fee waiver denied', payment_recorded: 'Payment recorded',
  fee_payment_recorded: 'External payment credited', fee_payment_reversed: 'External payment credit reversed',
  filing_date_assessed: 'Filing date assessed using court calendar',
  filing_date_ordered: 'Court-ordered filing date recorded',
  fee_review_requested: 'Fee review requested', fee_assessed: 'Court fee assessment recorded',
  public_copy_published: 'Reviewed public copy published',
  document_withheld: 'Document withheld from public access',
};

function saveReceipt(filingId: number, transaction: FilingTransaction) {
  const file = new Blob([JSON.stringify({ filing_id: filingId, ...transaction }, null, 2)], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(file);
  const link = document.createElement('a');
  link.href = url;
  link.download = `filing-${filingId}-receipt-${transaction.id}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function FilingHistoryPage() {
  const { filingId } = useParams();
  const [history, setHistory] = useState<FilingHistory | null>(null);
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<LoadFailure | null>(null);
  const role = getDemoRole();
  const backTo = role === 'admin' ? '/admin' : role === 'clerk' ? '/clerk/queue' : '/filings';

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await getFilingHistory(Number(filingId), page, controller.signal);
        if (!controller.signal.aborted) setHistory(result);
      } catch (err) {
        if (!controller.signal.aborted) setError(loadFailure(err, 'Could not load filing history. Receipts are available to the filer and court staff.'));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [filingId, page, attempt]);

  return <section className="filing-history">
    <div className="page-header">
      <div><h2>Filing #{filingId}: receipts &amp; history</h2>
        <p>Submission records and clerk decisions, newest first.</p></div>
      <Link className="btn btn-secondary" to={backTo}>
        {role === 'admin' ? 'People & access' : role === 'clerk' ? 'Back to queue' : 'My Filings'}
      </Link>
    </div>
    {loading && <p role="status">Loading filing history…</p>}
    {error && <LoadError failure={error} onRetry={() => setAttempt(n => n + 1)} />}
    {!loading && !error && history && <>
      <div className="history-summary">
        <span className={`status-badge ${history.status}`}>{history.status === 'served' ? 'Service documents recorded' : history.status.replace(/_/g, ' ')}</span>
        <span>{history.submission_count} recorded submission{history.submission_count === 1 ? '' : 's'}</span>
        <button className="btn btn-secondary btn-small" onClick={() => window.print()}>Print this page</button>
        <Link to={`/filings/${filingId}/fees`}>View fees &amp; payments</Link>
        <Link to={`/filings/${filingId}/deliveries`}>Document deliveries</Link>
      </div>
      <p className="info-text">A receipt records what this system received. Court acceptance is a separate decision.
        Times below are recorded in UTC. Service-only records do not prove delivery to another party.</p>
      <div className="review-card">
        <h3>Filing date: {formatCourtDate(history.filing_date)}</h3>
        {history.filing_date_basis && <FilingDateEvidence basis={history.filing_date_basis} />}
        {history.filing_date_basis?.source !== 'court_order' && <p>This date uses the court&apos;s published business-day calendar. It does not decide relief from
          a deadline, the effect of a correction, or timely payment after a fee-waiver denial.</p>
        }
        <div className="participant-actions">
          <Link to={`/courts/${history.court_id}/calendar`}>View court calendar and revisions</Link>
          {history.can_manage_documents && <Link to={`/filings/${filingId}/filing-date`}>Record a filing-date order</Link>}
        </div>
      </div>
      {history.fee_waiver && <FeeWaiverPanel key={`${filingId}-${attempt}`} filingId={history.filing_id}
        waiver={history.fee_waiver} onChange={() => { setPage(1); setAttempt(n => n + 1); }} />}
      {history.transactions.length === 0 && <div className="empty-state">
        <h3>No recorded transactions</h3>
        <p>Receipts are created when a filing is submitted. Filings that predate receipt tracking do not have reconstructed receipts.</p>
      </div>}
      <ol className="filing-timeline">
        {history.transactions.map(transaction => <li key={transaction.id} className="receipt-card">
          <div className="receipt-heading">
            <h3>{eventLabels[transaction.event_type] || transaction.event_type}</h3>
            <span>{transaction.submission_number ? `Submission ${transaction.submission_number}`
              : ['payment_recorded', 'fee_payment_recorded', 'fee_payment_reversed', 'fee_review_requested', 'fee_assessed'].includes(transaction.event_type) ? 'Before submission' : 'Legacy filing'}</span>
          </div>
          <p><time dateTime={parseServerDate(transaction.occurred_at).toISOString()}>
            {parseServerDate(transaction.occurred_at).toISOString().replace('T', ' ').replace('Z', ' UTC')}
          </time> · {transaction.actor_name}</p>
          <p className="receipt-reference">Transaction <code>{transaction.id}</code></p>
          {transaction.details.reason && <div className="alert alert-warning">{transaction.details.reason}</div>}
          {transaction.details.basis && <p>{waiverActionLabels[transaction.details.basis] || transaction.details.basis}</p>}
          {transaction.details.amount_due_cents != null && <p>Amount due under the decision: <strong>{formatCents(transaction.details.amount_due_cents)}</strong></p>}
          {transaction.details.items && <div className="fee-summary">
            {transaction.details.items.map((item, index) => <p key={index}>{item.description}: <strong>{formatCents(item.amount_cents)}</strong></p>)}
            <p>Assessed total: <strong>{formatCents(transaction.details.total_cents ?? 0)}</strong></p>
            <p>{transaction.details.authority_reference}</p>
          </div>}
          {transaction.details.filing_date_basis && <div className="receipt-date-basis">
            <p>Filing date at this transaction: <strong>{formatCourtDate(transaction.details.filing_date_basis.filing_date)}</strong></p>
            {'previous_filing_date' in transaction.details && <p>Previous filing date: {formatCourtDate(transaction.details.previous_filing_date ?? null)}</p>}
            <FilingDateEvidence basis={transaction.details.filing_date_basis} />
          </div>}
          {transaction.details.case_date_change && <p>Case opening date for {transaction.details.case_date_change.case_number}:
            {' '}{formatCourtDate(transaction.details.case_date_change.previous_filing_date)} → {formatCourtDate(transaction.details.case_date_change.filing_date)}.</p>}
          {['payment_recorded', 'fee_payment_recorded', 'fee_payment_reversed'].includes(transaction.event_type) && transaction.details.payment && <p>
            {formatCents(transaction.details.payment.amount_cents)} · {transaction.details.payment.transaction_ref}
            {transaction.details.payment.is_simulated && ' (simulated)'}
          </p>}
          {transaction.details.payment?.fee_basis && <p>
            Payment basis: {transaction.details.payment.fee_basis.source} · total {formatCents(transaction.details.payment.fee_basis.total_cents)}
            {' · '}previous payments {formatCents(transaction.details.payment.fee_basis.previous_paid_cents)}
            {transaction.details.payment.fee_basis.assessment_id && ` · assessment #${transaction.details.payment.fee_basis.assessment_id}`}
          </p>}
          {transaction.details.payment?.external_receipt && <p>
            External receipt: {transaction.details.payment.external_receipt.system} · {transaction.details.payment.external_receipt.reference}.
            {' '}Received {parseServerDate(transaction.details.payment.external_receipt.received_at).toLocaleString()}.
            {transaction.event_type === 'fee_payment_reversed' && ' This credit was reversed; the portal did not issue a refund.'}
          </p>}
          {transaction.details.court_name && <dl className="receipt-details">
            <div><dt>Court</dt><dd>{transaction.details.court_name}</dd></div>
            <div><dt>Case at submission</dt><dd>{transaction.details.case_title || 'Not specified'}
              {transaction.details.case_number && ` · ${transaction.details.case_number}`}</dd></div>
            <div><dt>Payment at submission</dt><dd>{transaction.details.payments
              ? transaction.details.payments.length ? <ul>{transaction.details.payments.map(payment => <li key={payment.id}>
                {formatCents(payment.amount_cents)} · {payment.transaction_ref} · {payment.status}{payment.is_simulated && ' (simulated)'}
                {payment.external_receipt && ` · ${payment.external_receipt.system}: ${payment.external_receipt.reference}`}
              </li>)}</ul> : transaction.details.fee_waiver_requested ? 'Fee waiver requested' : 'No payment recorded'
              : transaction.details.payment
              ? `${formatCents(transaction.details.payment.amount_cents)} · ${transaction.details.payment.transaction_ref}${transaction.details.payment.is_simulated ? ' (simulated)' : ''}`
              : transaction.details.fee_waiver_requested ? 'Fee waiver requested' : 'No payment recorded'}</dd></div>
          </dl>}
          {transaction.details.fee_assessment && <p>
            Fee record at submission: {transaction.details.fee_assessment.source}
            {' · '}total {transaction.details.fee_assessment.total_cents === null ? 'not established' : formatCents(transaction.details.fee_assessment.total_cents)}
            {' · '}completed payments {formatCents(transaction.details.fee_assessment.paid_cents)}
            {' · '}balance {transaction.details.fee_assessment.balance_due_cents === null ? 'not established' : formatCents(transaction.details.fee_assessment.balance_due_cents)}
          </p>}
          {transaction.details.cms_case_number && <p>Court case number: <strong>{transaction.details.cms_case_number}</strong></p>}
          {transaction.details.public_copy && transaction.details.document_id && <div className="receipt-documents">
            <h4>Public copy recorded at this transaction</h4>
            <p>{transaction.details.public_copy.title} · {formatBytes(transaction.details.public_copy.file_size_bytes)}</p>
            <DocumentDownload id={transaction.details.document_id} copyId={transaction.details.public_copy.id} title={transaction.details.public_copy.title} />
            <details><summary>Public copy fingerprint (SHA-256)</summary><code>{transaction.details.public_copy.sha256_hash}</code></details>
          </div>}
          {history.can_manage_documents && transaction.details.document_id && <p>
            <Link to={`/documents/${transaction.details.document_id}/publication`}>Manage document public access</Link>
          </p>}
          {transaction.details.documents && <>
            <h4>Documents recorded ({transaction.details.documents.length})</h4>
            <ul className="receipt-documents">{transaction.details.documents.map(doc => <li key={doc.id}>
              <div className="receipt-document-heading"><strong>{doc.title}</strong>
                <div className="participant-actions"><DocumentDownload id={doc.id} title={doc.title} />
                  {history.can_manage_documents && <Link to={`/documents/${doc.id}/publication`}>Manage public access</Link>}
                </div>
              </div>
              <p>{getDocumentLabel(doc.document_type_code)} · {formatBytes(doc.file_size_bytes)}{doc.is_confidential ? ' · Confidential' : ''}</p>
              <details><summary>Document fingerprint (SHA-256)</summary><code>{doc.sha256_hash}</code></details>
            </li>)}</ul>
          </>}
          <button className="btn btn-secondary btn-small" onClick={() => saveReceipt(history.filing_id, transaction)}>Download transaction JSON</button>
        </li>)}
      </ol>
      {history.total > history.page_size && <nav className="pagination" aria-label="Filing history pages">
        <button className="btn btn-secondary" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</button>
        <span>Page {page} of {Math.ceil(history.total / history.page_size)}</span>
        <button className="btn btn-secondary" disabled={page * history.page_size >= history.total} onClick={() => setPage(p => p + 1)}>Next</button>
      </nav>}
    </>}
  </section>;
}
