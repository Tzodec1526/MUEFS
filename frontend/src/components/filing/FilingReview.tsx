import { useState } from 'react';
import { submitFiling, validateFiling, FilingValidation } from '../../api/filings';

interface FilingData {
  courtId: number | null;
  courtName: string;
  caseTypeId: number | null;
  caseTypeName: string;
  caseTitle: string;
  filingDescription: string;
  filingId: number | null;
  documents: Array<{ id: number; title: string; type: string; size: number }>;
  serviceContacts: Array<{ name: string; email: string; method: string }>;
}

interface Props {
  filingData: FilingData;
  filingId: number | null;
}

function FilingReview({ filingData, filingId }: Props) {
  const [validation, setValidation] = useState<FilingValidation | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleValidate = async () => {
    if (!filingId) return;
    try {
      const result = await validateFiling(filingId);
      setValidation(result);
    } catch {
      setError('Validation failed');
    }
  };

  const handleSubmit = async () => {
    if (!filingId) return;
    setSubmitting(true);
    setError(null);
    try {
      await submitFiling(filingId);
      setSubmitted(true);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Submission failed';
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="form-section success-section">
        <h3>Filing Submitted Successfully</h3>
        <p>
          Your filing has been submitted to <strong>{filingData.courtName}</strong> for review.
          You will receive an email notification when the clerk reviews your filing.
        </p>
        <p>Filing ID: <strong>#{filingId}</strong></p>
        <a href="/" className="btn btn-primary">Return to Dashboard</a>
      </div>
    );
  }

  return (
    <div className="form-section">
      <h3>Review Your Filing</h3>
      <p className="info-text">
        Please review all information before submitting. Once submitted,
        the filing will be sent to the court clerk for review.
      </p>

      <div className="review-summary">
        <div className="review-item">
          <label>Court:</label>
          <span>{filingData.courtName || 'Not selected'}</span>
        </div>
        <div className="review-item">
          <label>Case Type:</label>
          <span>{filingData.caseTypeName || 'Not selected'}</span>
        </div>
        <div className="review-item">
          <label>Case Title:</label>
          <span>{filingData.caseTitle || 'Not provided'}</span>
        </div>
        <div className="review-item">
          <label>Description:</label>
          <span>{filingData.filingDescription || 'Not provided'}</span>
        </div>
        <div className="review-item">
          <label>Documents:</label>
          <span>{filingData.documents.length} document(s) uploaded</span>
        </div>
        <div className="review-item">
          <label>Service Contacts:</label>
          <span>{filingData.serviceContacts.length} contact(s)</span>
        </div>
      </div>

      {/* Validation Results */}
      {validation && (
        <div className={`validation-results ${validation.is_valid ? 'valid' : 'invalid'}`}>
          <h4>{validation.is_valid ? 'Validation Passed' : 'Validation Issues Found'}</h4>
          {validation.errors.length > 0 && (
            <div className="validation-errors">
              <h5>Errors (must fix):</h5>
              <ul>
                {validation.errors.map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
              </ul>
            </div>
          )}
          {validation.missing_required_documents.length > 0 && (
            <div className="validation-missing">
              <h5>Missing Required Documents:</h5>
              <ul>
                {validation.missing_required_documents.map((doc, i) => (
                  <li key={i}>{doc}</li>
                ))}
              </ul>
            </div>
          )}
          {validation.warnings.length > 0 && (
            <div className="validation-warnings">
              <h5>Warnings:</h5>
              <ul>
                {validation.warnings.map((warn, i) => (
                  <li key={i}>{warn}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {error && <div className="alert alert-error">{error}</div>}

      <div className="review-actions">
        <button className="btn btn-secondary" onClick={handleValidate}>
          Validate Filing
        </button>
        <button
          className="btn btn-primary"
          onClick={handleSubmit}
          disabled={submitting}
        >
          {submitting ? 'Submitting...' : 'Submit Filing'}
        </button>
      </div>
    </div>
  );
}

export default FilingReview;
