import { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { getFiling, submitFiling, validateFiling, FilingValidation, FilingEnvelope } from '../../api/filings';
import { formatBytes, getDocumentLabel } from '../../utils/format';
import { getErrorDetail } from '../../utils/errors';
import DocumentDownload from '../common/DocumentDownload';
import LoadError from '../common/LoadError';
import PaymentForm from './PaymentForm';

interface Props {
  filingId: number;
  courtName: string;
  caseTypeName: string;
  submission?: FilingEnvelope;
  onFeesChange?: (filing: FilingEnvelope, obligationMet: boolean) => void;
  onSubmitSuccess?: (filing: FilingEnvelope) => void;
  onSubmittingChange?: (submitting: boolean) => void;
  readOnly?: boolean;
}

function FilingReview({ filingId, courtName, caseTypeName, submission, onFeesChange, onSubmitSuccess, onSubmittingChange, readOnly = false }: Props) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{
    key: string; filing?: FilingEnvelope; validation?: FilingValidation | null; error?: string;
  }>();
  const [fees, setFees] = useState<{ key: string; token: string; obligationMet: boolean }>();
  const [submitting, setSubmitting] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submissionKey = useRef<string | null>(null);
  const key = `${filingId}:${attempt}:${readOnly}`;
  const current = result?.key === key ? result : undefined;
  const filing = current?.filing;
  const validation = current?.validation;
  const canSubmit = !readOnly && (filing?.status === 'draft' || filing?.status === 'returned');
  const currentFees = fees?.key === key ? fees : undefined;
  const needsPayment = filing?.filing_type !== 'service_only' && !currentFees?.obligationMet;
  const needsRefresh = conflict || (currentFees && currentFees.token !== filing?.submission_token);

  useEffect(() => {
    if (submission) return;
    const controller = new AbortController();
    Promise.all([
      getFiling(filingId, controller.signal),
      readOnly ? Promise.resolve(null) : validateFiling(filingId, controller.signal),
    ]).then(([filing, validation]) => {
      if (!controller.signal.aborted) setResult({ key, filing, validation });
    }).catch(err => {
      if (!controller.signal.aborted) setResult({ key, error: getErrorDetail(err) || 'Could not load the saved filing for review.' });
    });
    return () => controller.abort();
  }, [filingId, key, readOnly, submission]);

  const handleFeesChange = useCallback((updated: FilingEnvelope, obligationMet: boolean) => {
    setFees({ key, token: updated.submission_token, obligationMet });
    onFeesChange?.(updated, obligationMet);
  }, [key, onFeesChange]);

  function refreshReview() {
    setError(null);
    setConflict(false);
    setAttempt(previous => previous + 1);
  }

  const handleSubmit = async () => {
    if (!filing || !canSubmit || needsRefresh || needsPayment || !validation?.is_valid) return;
    setSubmitting(true);
    onSubmittingChange?.(true);
    setError(null);
    try {
      submissionKey.current ??= crypto.randomUUID();
      const result = await submitFiling(filingId, filing.submission_token, submissionKey.current);
      onSubmitSuccess?.(result);
    } catch (err: unknown) {
      if ((err as { response?: { status?: number } }).response?.status === 409) setConflict(true);
      setError(getErrorDetail(err) || 'Submission could not be confirmed. Retry to check the same submission.');
    } finally {
      setSubmitting(false);
      onSubmittingChange?.(false);
    }
  };

  if (submission) {
    return (
      <div className="form-section success-section">
        <div className="success-icon">&#10003;</div>
        <h3>{submission.status === 'served' ? 'Service Documents Recorded'
          : submission.status === 'submitted' ? 'Filing Submitted Successfully' : 'Submission Already Recorded'}</h3>
        <p>
          {submission.status === 'served'
            ? 'This service-only filing has been recorded. It does not enter clerk review or deliver documents to other parties.'
            : <>Your submission to <strong>{courtName}</strong> was recorded. Check the current status below and view the receipt for the submitted documents.</>}
        </p>
        <div className="success-details">
          <div className="success-detail-row">
            <span>Filing ID</span>
            <strong>#{filingId}</strong>
          </div>
          <div className="success-detail-row">
            <span>Case</span>
            <strong>{submission.case_title}</strong>
          </div>
          <div className="success-detail-row">
            <span>Documents</span>
            <strong>{submission.documents.length}</strong>
          </div>
          <div className="success-detail-row">
            <span>Status</span>
            <span className={`status-badge ${submission.status}`}>{submission.status.replace('_', ' ')}</span>
          </div>
        </div>
        <p className="success-note">
          You can track the status of your filing from your dashboard under &quot;My Filings.&quot;
        </p>
        <div className="success-actions">
          <Link to={`/filings/${filingId}/history`} className="btn btn-primary">View submission receipt</Link>
          <a href="/" className="btn btn-primary">Return to Dashboard</a>
          <a href="/filing/new" className="btn btn-secondary">File Another</a>
        </div>
      </div>
    );
  }

  if (!current) return <p role="status">Loading the saved filing for review…</p>;
  if (current.error) return <LoadError message={current.error} onRetry={refreshReview} />;
  if (!filing) return null;

  return (
    <div className="form-section">
      <h3>{canSubmit ? 'Review Your Filing' : 'Filing Details'}</h3>
      {canSubmit && (
        <p className="info-text">
          Review all information carefully before submitting. Submitted filings
          cannot be edited unless returned for correction.
        </p>
      )}

      {!canSubmit && !readOnly && <p className="alert alert-warning" role="status">
        This filing is now {filing.status.replace('_', ' ')}. <Link to={`/filings/${filingId}/history`}>View its receipt and current status</Link>.
      </p>}

      {/* Filing Summary */}
      <div className="review-card">
        <h4>Court & Case Information</h4>
        <div className="review-grid">
          <div className="review-item">
            <label>Court</label>
            <span>{courtName || 'Not selected'}</span>
          </div>
          <div className="review-item">
            <label>Case Type</label>
            <span>{caseTypeName || 'Not selected'}</span>
          </div>
          <div className="review-item">
            <label>Case Title</label>
            <span>{filing.case_title || 'Not provided'}</span>
          </div>
        </div>
        {filing.filing_description && (
          <div className="review-item full-width">
            <label>Description</label>
            <span>{filing.filing_description}</span>
          </div>
        )}
      </div>

      {/* Documents */}
      <div className="review-card">
        <h4>Documents ({filing.documents.length})</h4>
        {filing.documents.length > 0 ? (
          <table className="review-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Size</th>
                <th>Text Searchable</th>
                <th>Confidential</th>
              </tr>
            </thead>
            <tbody>
              {filing.documents.map((doc) => (
                <tr key={doc.id}>
                  <td>{doc.title} <DocumentDownload id={doc.id} title={doc.title} /></td>
                  <td>{getDocumentLabel(doc.document_type_code)}</td>
                  <td>{formatBytes(doc.file_size_bytes)}</td>
                  <td>{doc.is_text_searchable ? 'Yes' : <span className="warning-text">No</span>}</td>
                  <td>{doc.is_confidential ? 'Yes' : 'No'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="warning-text">No documents uploaded.</p>
        )}
      </div>

      {filing.filing_type === 'service_only' && (
        <p className="info-text">Recording this filing does not deliver documents to other parties. Arrange service outside this app.</p>
      )}

      {canSubmit && filing.filing_type !== 'service_only' && filingId && (
        <PaymentForm
          filingId={filingId}
          onFeesChange={handleFeesChange}
        />
      )}

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

      {needsRefresh && <p className="alert alert-warning" role="alert">
        The filing or fee state changed. Refresh the review and check the saved details and documents before submitting.
      </p>}
      {error && <div className="alert alert-error" role="alert">{error}</div>}

      {canSubmit && (
        <>
          <div className="review-actions">
            <button className="btn btn-secondary" onClick={refreshReview} disabled={submitting}>
              Refresh Review
            </button>
            <button
              className="btn btn-primary btn-large"
              onClick={handleSubmit}
              disabled={submitting || Boolean(needsRefresh) || needsPayment || !validation?.is_valid}
              title={
                needsRefresh
                  ? 'Refresh and review the changed filing before submitting'
                  : needsPayment
                  ? 'Complete payment above before submitting'
                  : !validation || !validation.is_valid
                    ? 'Resolve the issues above before submitting'
                    : undefined
              }
            >
              {submitting ? 'Submitting...' : 'Submit Filing'}
            </button>
          </div>

          <p className="submit-disclaimer">
            By submitting, you certify under MCR 1.109 that this filing complies with
            Michigan Court Rules, that all documents are text-searchable, and that
            personal identifying information has been properly redacted.
          </p>
        </>
      )}
    </div>
  );
}

export default FilingReview;
