import { useState, useEffect } from 'react';
import { getCaseTypes, getFilingRequirements, CaseType, FilingRequirement } from '../../api/courts';

interface Props {
  courtId: number;
  selectedCaseTypeId: number | null;
  onSelect: (caseTypeId: number, caseTypeName: string) => void;
}

function CaseTypeSelector({ courtId, selectedCaseTypeId, onSelect }: Props) {
  const [caseTypes, setCaseTypes] = useState<CaseType[]>([]);
  const [requirements, setRequirements] = useState<FilingRequirement[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function fetchCaseTypes() {
      setLoading(true);
      try {
        const types = await getCaseTypes(courtId);
        setCaseTypes(types);
      } catch {
        setCaseTypes([]);
      } finally {
        setLoading(false);
      }
    }
    fetchCaseTypes();
  }, [courtId]);

  useEffect(() => {
    if (!selectedCaseTypeId) {
      setRequirements([]);
      return;
    }
    async function fetchRequirements() {
      try {
        const reqs = await getFilingRequirements(courtId, selectedCaseTypeId!);
        setRequirements(reqs);
      } catch {
        setRequirements([]);
      }
    }
    fetchRequirements();
  }, [courtId, selectedCaseTypeId]);

  const formatFee = (cents: number) => {
    return `$${(cents / 100).toFixed(2)}`;
  };

  return (
    <div className="form-section">
      <h3>Select Case Type</h3>
      <p className="info-text">
        Choose the type of case for your filing. Filing fees and required documents
        vary by case type.
      </p>

      {loading && <p>Loading case types...</p>}

      <div className="case-type-list">
        {caseTypes.map((ct) => (
          <div
            key={ct.id}
            className={`case-type-card ${selectedCaseTypeId === ct.id ? 'selected' : ''}`}
            onClick={() => onSelect(ct.id, ct.name)}
          >
            <div className="case-type-header">
              <h4>{ct.name}</h4>
              <span className="case-type-fee">{formatFee(ct.filing_fee_cents)}</span>
            </div>
            <p className="case-type-category">{ct.category}</p>
            {ct.description && <p>{ct.description}</p>}
          </div>
        ))}
      </div>

      {/* Filing Requirements - shown after selecting a case type */}
      {selectedCaseTypeId && requirements.length > 0 && (
        <div className="requirements-section">
          <h4>Filing Requirements</h4>
          <p className="info-text">
            The following documents are needed for this filing type.
            Required items must be included for your filing to be accepted.
          </p>
          <table className="requirements-table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Required</th>
                <th>MCR Reference</th>
                <th>Page Limit</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {requirements.map((req) => (
                <tr key={req.id} className={req.is_required ? 'required' : ''}>
                  <td>
                    <strong>{req.description}</strong>
                    <br />
                    <code>{req.document_type_code}</code>
                  </td>
                  <td>{req.is_required ? 'Required' : 'Optional'}</td>
                  <td>
                    {req.mcr_reference && (
                      <span className="mcr-ref">{req.mcr_reference}</span>
                    )}
                    {req.local_rule_reference && (
                      <span className="local-rule">{req.local_rule_reference}</span>
                    )}
                  </td>
                  <td>{req.page_limit ? `${req.page_limit} pages` : 'N/A'}</td>
                  <td>{req.format_notes || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default CaseTypeSelector;
