import { useState, useEffect } from 'react';
import { getCaseTypes, getFilingRequirements, CaseType, FilingRequirement } from '../../api/courts';

interface Props {
  courtId: number;
  selectedCaseTypeId: number | null;
  onSelect: (caseTypeId: number, caseTypeName: string, filingFeeCents: number) => void;
}

function CaseTypeSelector({ courtId, selectedCaseTypeId, onSelect }: Props) {
  const [caseTypes, setCaseTypes] = useState<CaseType[]>([]);
  const [requirements, setRequirements] = useState<FilingRequirement[]>([]);
  const [loading, setLoading] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

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
    if (cents === 0) return 'No fee';
    return `$${(cents / 100).toFixed(2)}`;
  };

  const categories = [...new Set(caseTypes.map(ct => ct.category))];

  const filtered = caseTypes.filter(ct => {
    if (categoryFilter && ct.category !== categoryFilter) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return ct.name.toLowerCase().includes(q) || ct.code.toLowerCase().includes(q);
    }
    return true;
  });

  const requiredDocs = requirements.filter(r => r.is_required);
  const optionalDocs = requirements.filter(r => !r.is_required);

  return (
    <div className="form-section">
      <h3>Select Case Type & Review Requirements</h3>
      <p className="info-text">
        Choose the type of case for your filing. After selecting, review the filing
        requirements below to ensure you have all necessary documents.
      </p>

      {/* Filters */}
      <div className="filter-row">
        <div className="form-group">
          <label htmlFor="categoryFilter">Category</label>
          <select
            id="categoryFilter"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
          >
            <option value="">All Categories</option>
            {categories.map(c => (
              <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label htmlFor="typeSearch">Search</label>
          <input
            id="typeSearch"
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search case types..."
          />
        </div>
      </div>

      {loading && <p>Loading case types...</p>}

      <div className="case-type-list">
        {filtered.map((ct) => (
          <div
            key={ct.id}
            className={`case-type-card ${selectedCaseTypeId === ct.id ? 'selected' : ''}`}
            onClick={() => onSelect(ct.id, ct.name, ct.filing_fee_cents)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onSelect(ct.id, ct.name, ct.filing_fee_cents); }}
            aria-selected={selectedCaseTypeId === ct.id}
          >
            <div className="case-type-header">
              <h4>{ct.name}</h4>
              <span className={`case-type-fee ${ct.filing_fee_cents === 0 ? 'fee-free' : ''}`}>
                {formatFee(ct.filing_fee_cents)}
              </span>
            </div>
            <div className="case-type-meta">
              <span className="case-type-category">{ct.category}</span>
              <span className="case-type-code">{ct.code}</span>
            </div>
            {ct.description && <p className="case-type-desc">{ct.description}</p>}
          </div>
        ))}
        {!loading && filtered.length === 0 && (
          <p className="no-results">No case types match your filters.</p>
        )}
      </div>

      {/* Filing Requirements - shown after selecting a case type */}
      {selectedCaseTypeId && requirements.length > 0 && (
        <div className="requirements-section">
          <h4>Filing Requirements & Court Rules</h4>
          <p className="info-text">
            Review these requirements carefully. Missing required documents will
            cause your filing to be rejected by the clerk.
          </p>

          {requiredDocs.length > 0 && (
            <div className="requirements-group">
              <h5 className="req-group-header req-required">Required Documents ({requiredDocs.length})</h5>
              <div className="requirements-cards">
                {requiredDocs.map((req) => (
                  <div key={req.id} className="requirement-card required">
                    <div className="req-card-header">
                      <span className="req-badge required">Required</span>
                      {req.mcr_reference && (
                        <span className="mcr-ref">{req.mcr_reference}</span>
                      )}
                    </div>
                    <h5>{req.description}</h5>
                    <code className="req-code">{req.document_type_code}</code>
                    {req.page_limit && (
                      <p className="req-detail">Page limit: {req.page_limit} pages</p>
                    )}
                    {req.format_notes && (
                      <p className="req-detail">{req.format_notes}</p>
                    )}
                    {req.local_rule_reference && (
                      <p className="req-detail">Local Rule: {req.local_rule_reference}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {optionalDocs.length > 0 && (
            <div className="requirements-group">
              <h5 className="req-group-header req-optional">Optional Documents ({optionalDocs.length})</h5>
              <div className="requirements-cards">
                {optionalDocs.map((req) => (
                  <div key={req.id} className="requirement-card optional">
                    <div className="req-card-header">
                      <span className="req-badge optional">Optional</span>
                      {req.mcr_reference && (
                        <span className="mcr-ref">{req.mcr_reference}</span>
                      )}
                    </div>
                    <h5>{req.description}</h5>
                    <code className="req-code">{req.document_type_code}</code>
                    {req.format_notes && (
                      <p className="req-detail">{req.format_notes}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default CaseTypeSelector;
