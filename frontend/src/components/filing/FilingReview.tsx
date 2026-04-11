import { useState } from 'react';
import { submitFiling, validateFiling, FilingValidation } from '../../api/filings';

interface FilingData {
  courtId: number | null;
  courtName: string;
  caseTypeId: number | null;
  caseTypeName: string;
  filingFeeCents: number;
  caseTitle: string;
  filingDescription: string;
  filingId: number | null;
  documents: Array<{ id: number; title: string; type: string; size: number; isSearchable: boolean }>;
  serviceContacts: Array<{ name: string; email: string; method: string }>;
  paymentComplete: boolean;
}

interface Props {
  filingData: FilingData;
  filingId: number | null;
  onSubmitSuccess?: () => void;
}

function FilingReview({ filingData, filingId, onSubmitSuccess }: Props) {
  const [validation, setValidation] = useState<FilingValidation | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleValidate = async () => {
    if (!filingId) return;
    setError(null);
    try {
      const result = await validateFiling(filingId);
      setValidation(result);
    } catch {
      setError('Validation failed. Please try again.');
    }
  };

  const handleSubmit = async () => {
    if (!filingId) return;
    setSubmitting(true);
    setError(null);
    try {
      await submitFiling(filingId);
      setSubmitted(true);
      onSubmitSuccess?.();
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      const detail = axiosErr?.response?.data?.detail;
      const message = detail || (err instanceof Error ? err.message : 'Submission failed. Please try again.');
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  };

  const formatFee = (cents: number) => cents === 0 ? 'No fee' : `$${(cents / 100).toFixed(2)}`;

  if (submitted) {
    return (
      <div className="form-section success-section">
        <div className="success-icon">&#10003;</div>
        <h3>Filing Submitted Successfully</h3>
        <p>
          Your filing has been submitted to <strong>{filingData.courtName}</strong> for clerk review.
        </p>
        <div className="success-details">
          <div className="success-detail-row">
            <span>Filing ID</span>
            <strong>#{filingId}</strong>
          </div>
          <div className="success-detail-row">
            <span>Case</span>
            <strong>{filingData.caseTitle}</strong>
          </div>
          <div className="success-detail-row">
            <span>Documents</span>
            <strong>{filingData.documents.length}</strong>
          </div>
          <div className="success-detail-row">
            <span>Status</span>
            <span className="status-badge submitted">Submitted</span>
          </div>
        </div>
        <p className="success-note">
          You can track the status of your filing from your dashboard under "My Filings."
        </p>
        <div className="success-actions">
          <a href="/" className="btn btn-primary">Return to Dashboard</a>
          <a href="/filing/new" className="btn btn-secondary">File Another</a>
        </div>
      </div>
    );
  }

  return (
    <div className="form-section">
      <h3>Review Your Filing</h3>
      <p className="info-text">
        Please review all information carefully before submitting. Once submitted,
        the filing will be sent to the court clerk for review.
      </p>

      {/* Filing Summary */}
      <div className="review-card">
        <h4>Court & Case Information</h4>
        <div className="review-grid">
          <div className="review-item">
            <label>Court</label>
            <span>{filingData.courtName || 'Not selected'}</span>
          </div>
          <div className="review-item">
            <label>Case Type</label>
            <span>{filingData.caseTypeName || 'Not selected'}</span>
          </div>
          <div className="review-item">
            <label>Case Title</label>
            <span>{filingData.caseTitle || 'Not provided'}</span>
          </div>
          <div className="review-item">
            <label>Filing Fee</label>
            <span>{formatFee(filingData.filingFeeCents)}</span>
          </div>
        </div>
        {filingData.filingDescription && (
          <div className="review-item full-width">
            <label>Description</label>
            <span>{filingData.filingDescription}</span>
          </div>
        )}
      </div>

      {/* Documents */}
      <div className="review-card">
        <h4>Documents ({filingData.documents.length})</h4>
        {filingData.documents.length > 0 ? (
          <table className="review-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Size</th>
                <th>Text Searchable</th>
              </tr>
            </thead>
            <tbody>
              {filingData.documents.map((doc) => (
                <tr key={doc.id}>
                  <td>{doc.title}</td>
                  <td><code>{doc.type}</code></td>
                  <td>{formatSize(doc.size)}</td>
                  <td>{doc.isSearchable ? 'Yes' : <span className="warning-text">No</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="warning-text">No documents uploaded.</p>
        )}
      </div>

      {/* Service Contacts */}
      <div className="review-card">
        <h4>Service of Process ({filingData.serviceContacts.length})</h4>
        {filingData.serviceContacts.length > 0 ? (
          <table className="review-table">
            <thead>
              <tr><th>Name</th><th>Email</th><th>Method</th></tr>
            </thead>
            <tbody>
              {filingData.serviceContacts.map((c, i) => (
                <tr key={i}>
                  <td>{c.name}</td>
                  <td>{c.email}</td>
                  <td>{c.method}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="info-text">No service contacts added. You may need to serve parties through traditional methods.</p>
        )}
      </div>

      {/* Validation Results */}
      {validation && (
        <div className={`validation-results ${validation.is_valid ? 'valid' : 'invalid'}`} role="alert">
          <h4>{validation.is_valid ? 'Validation Passed' : 'Issues Found'}</h4>
          {validation.errors.length > 0 && (
            <div className="validation-errors">
              <h5>Errors (must fix before submitting):</h5>
              <ul>
                {validation.errors.map((err, i) => <li key={i}>{err}</li>)}
              </ul>
            </div>
          )}
          {validation.missing_required_documents.length > 0 && (
            <div className="validation-missing">
              <h5>Missing Required Documents:</h5>
              <ul>
                {validation.missing_required_documents.map((doc, i) => <li key={i}>{doc}</li>)}
              </ul>
            </div>
          )}
          {validation.warnings.length > 0 && (
            <div className="validation-warnings">
              <h5>Warnings:</h5>
              <ul>
                {validation.warnings.map((warn, i) => <li key={i}>{warn}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {error && <div className="alert alert-error" role="alert">{error}</div>}

      <div className="review-actions">
        <button className="btn btn-secondary" onClick={handleValidate}>
          Validate Before Submitting
        </button>
        <button
          className="btn btn-primary btn-large"
          onClick={handleSubmit}
          disabled={submitting || (validation !== null && !validation.is_valid)}
        >
          {submitting ? 'Submitting to Court...' : 'Submit Filing'}
        </button>
      </div>

      <p className="submit-disclaimer">
        By submitting, you certify under MCR 1.109 that this filing complies with
        Michigan Court Rules, that all documents are text-searchable, and that
        personal identifying information has been properly redacted.
      </p>
    </div>
  );
}

export default FilingReview;
