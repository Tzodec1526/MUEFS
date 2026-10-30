import { useState, type FormEvent } from 'react';
import { apiClient } from '../../api/client';
import type { FilingFees } from '../../api/documents';
import type { FilingEnvelope } from '../../api/filings';
import { getDocumentLabel } from '../../utils/documentTypes';
import { formatBytes, formatCents } from '../../utils/format';
import { filingStatusLabel, filingTypeLabel } from '../../utils/filingStatus';
import { errorMessage } from '../../utils/errors';
import DocumentDownload from '../common/DocumentDownload';

export default function FeeAssessmentForm({ fees, filing, onSaved }: {
  fees: FilingFees; filing: FilingEnvelope; onSaved: () => void;
}) {
  const [items, setItems] = useState([{ key: crypto.randomUUID(), code: '', description: '', amount: '' }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const amounts = items.map(item => {
      const [dollars, cents = ''] = item.amount.split('.');
      return { fee_type: item.code, description: item.description,
        amount_cents: Number(dollars) * 100 + Number(cents.padEnd(2, '0')) };
    });
    setBusy(true); setError('');
    try {
      await apiClient.post(`/clerk/filings/${filing.id}/fees`, {
        expected_version: fees.version, authority_reference: form.get('authority'),
        reason: form.get('reason'), reviewed: form.get('reviewed') === 'on', items: amounts,
      });
      onSaved();
    } catch (err) {
      setError(errorMessage(err, 'Could not confirm the assessment. Check history before retrying.'));
    } finally { setBusy(false); }
  }
  return <form className="fee-assessment-form" onSubmit={save}>
    <h3>Record a court fee assessment</h3>
    <p><strong>{filing.case_title || `Filing #${filing.id}`}</strong> · {filingTypeLabel(filing.filing_type)} · {filingStatusLabel(filing.status)}</p>
    {filing.filing_description && <p>{filing.filing_description}</p>}
    {fees.review_reason && <p className="alert alert-info"><strong>Filer’s reason for review:</strong> {fees.review_reason}</p>}
    <p>Review the current documents and applicable fees and exemptions. Include each charge once.
      A zero-dollar assessment requires an item explaining why no fee is due.</p>
    <ul className="receipt-documents">{filing.documents.map(doc => <li key={doc.id}>
      <div className="receipt-document-heading"><strong>{doc.title}</strong><DocumentDownload id={doc.id} title={doc.title} /></div>
      <p>{getDocumentLabel(doc.document_type_code)} · {formatBytes(doc.file_size_bytes)}</p>
    </li>)}</ul>
    {fees.paid_cents > 0 && <p>Completed payments already recorded: <strong>{formatCents(fees.paid_cents)}</strong>.
      Enter the full assessed total. The payment screen will deduct the recorded payments.</p>}
    <fieldset disabled={busy}>
      <legend>Itemized fees</legend>
      {items.map((item, index) => <div className="fee-assessment-item" key={item.key}>
        <div className="form-group"><label htmlFor={`fee-code-${item.key}`}>Fee code {index + 1}</label>
          <input id={`fee-code-${item.key}`} required maxLength={100} value={item.code}
            onChange={event => setItems(rows => rows.map(row => row.key === item.key ? { ...row, code: event.target.value } : row))} /></div>
        <div className="form-group"><label htmlFor={`fee-description-${item.key}`}>Description {index + 1}</label>
          <input id={`fee-description-${item.key}`} required maxLength={1000} value={item.description}
            onChange={event => setItems(rows => rows.map(row => row.key === item.key ? { ...row, description: event.target.value } : row))} /></div>
        <div className="form-group"><label htmlFor={`fee-amount-${item.key}`}>Amount {index + 1} (USD)</label>
          <input id={`fee-amount-${item.key}`} required inputMode="decimal" pattern="[0-9]{1,7}(\.[0-9]{1,2})?" value={item.amount}
            onChange={event => setItems(rows => rows.map(row => row.key === item.key ? { ...row, amount: event.target.value } : row))} /></div>
        {items.length > 1 && <button className="btn btn-secondary btn-small" type="button" onClick={() => setItems(rows => rows.filter(row => row.key !== item.key))}>Remove fee {index + 1}</button>}
      </div>)}
      <button className="btn btn-secondary" type="button" disabled={items.length >= 50}
        onClick={() => setItems(rows => [...rows, { key: crypto.randomUUID(), code: '', description: '', amount: '' }])}>Add fee item</button>
      <div className="form-group"><label htmlFor="fee-authority">Authority or approved schedule reference</label>
        <input id="fee-authority" name="authority" required maxLength={1000} /></div>
      <div className="form-group"><label htmlFor="fee-reason">Assessment reason, including any applicable exceptions</label>
        <textarea id="fee-reason" name="reason" required maxLength={5000} rows={3} /></div>
      <label className="checkbox-label"><input type="checkbox" name="reviewed" required />
        I reviewed the documents, charges and exceptions and confirm this is the full amount assessed by the court.</label>
      {error && <p className="alert alert-error" role="alert">{error}</p>}
      <button className="btn btn-primary" type="submit">{busy ? 'Recording assessment…' : 'Record fee assessment'}</button>
    </fieldset>
  </form>;
}
