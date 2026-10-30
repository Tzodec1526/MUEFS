import { useState, useEffect } from 'react';
import { getCaseTypes, getFilingRequirements, CaseType, FilingRequirement } from '../../api/courts';
import { formatFee } from '../../utils/format';
import LoadError from '../common/LoadError';
import { loadFailure, type LoadFailure } from '../../utils/errors';

function getRuleUrl(ref: string): string | null {
  const base = 'https://courts.michigan.gov/courts/michigansupremecourt/rules/court-rules-702';
  const rules: Record<string, string> = {
    'MCR 2.102': `${base}/chapter-2-civil-procedure/subchapter-2100-pleadings-and-motions/rule-2102-commencement-of-actions-and-service`,
    'MCR 2.104': `${base}/chapter-2-civil-procedure/subchapter-2100-pleadings-and-motions/rule-2104-proof-of-service`,
    'MCR 2.107': `${base}/chapter-2-civil-procedure/subchapter-2100-pleadings-and-motions/rule-2107-service-and-filing-of-pleadings-and-other-papers`,
    'MCR 2.111': `${base}/chapter-2-civil-procedure/subchapter-2100-pleadings-and-motions/rule-2111-general-rules-of-pleading`,
    'MCR 2.116': `${base}/chapter-2-civil-procedure/subchapter-2100-pleadings-and-motions/rule-2116-summary-disposition`,
    'MCR 2.119': `${base}/chapter-2-civil-procedure/subchapter-2100-pleadings-and-motions/rule-2119-motion-practice`,
    'MCR 2.119(F)': `${base}/chapter-2-civil-procedure/subchapter-2100-pleadings-and-motions/rule-2119-motion-practice`,
    'MCR 2.506': `${base}/chapter-2-civil-procedure/subchapter-2500-discovery/rule-2506-subpoena-order-to-attend`,
    'MCR 2.508': `${base}/chapter-2-civil-procedure/subchapter-2500-discovery/rule-2508-demand-for-jury-trial`,
    'MCR 8.119': `${base}/chapter-8-administrative-rules-of-court/subchapter-8100-general-administrative-orders/rule-8119-court-records-and-reports`,
    'MCR 1.109': `${base}/chapter-1-applicability-and-definitions/rule-1109-court-records-defined-documents`,
    'MCR 2.002': `${base}/chapter-2-civil-procedure/subchapter-2000-general-provisions/rule-2002-waiver-suspension-of-fees-and-costs`,
    'MCR 3.310': `${base}/chapter-3-special-proceedings-and-actions/subchapter-3300-provisional-and-final-remedies-and-special-proceedings/rule-3310-injunctions`,
    'MCR 2.612': `${base}/chapter-2-civil-procedure/subchapter-2600-judgment/rule-2612-relief-from-judgment-or-order`,
    'MCR 2.114': `${base}/chapter-2-civil-procedure/subchapter-2100-pleadings-and-motions/rule-2114-signing-of-pleadings-affidavits-and-other-papers-representations-to-court-sanctions`,
  };

  if (rules[ref]) return rules[ref];

  const baseRef = ref.replace(/\(.*/, '').trim();
  if (rules[baseRef]) return rules[baseRef];

  if (ref.startsWith('MCL ')) {
    const section = ref.replace('MCL ', '').replace(/\s/g, '');
    return `http://www.legislature.mi.gov/doc.aspx?mcl-${section}`;
  }

  return null;
}

const RULES = 'https://courts.michigan.gov/courts/michigansupremecourt/rules/court-rules-702';
const COURT_RULE_LINKS = [
  [`${RULES}/chapter-1-applicability-and-definitions/rule-1109-court-records-defined-documents`, 'MCR 1.109 - E-Filing & Document Standards'],
  [`${RULES}/chapter-2-civil-procedure/subchapter-2100-pleadings-and-motions/rule-2111-general-rules-of-pleading`, 'MCR 2.111 - General Rules of Pleading'],
  [`${RULES}/chapter-2-civil-procedure/subchapter-2100-pleadings-and-motions/rule-2116-summary-disposition`, 'MCR 2.116 - Summary Disposition'],
  [`${RULES}/chapter-2-civil-procedure/subchapter-2100-pleadings-and-motions/rule-2119-motion-practice`, 'MCR 2.119 - Motion Practice'],
  [`${RULES}/chapter-2-civil-procedure/subchapter-2500-discovery/rule-2506-subpoena-order-to-attend`, 'MCR 2.506 - Subpoenas'],
  ['http://www.legislature.mi.gov/doc.aspx?mcl-600-2163a', 'MCL 600.2163a - Uniform Interstate Depositions Act'],
  [RULES, 'Full Michigan Court Rules'],
];

function RequirementList({ requirements }: { requirements: FilingRequirement[] }) {
  return (
    <ul className="requirement-list">
      {requirements.map((req) => {
        const url = req.mcr_reference && getRuleUrl(req.mcr_reference);
        return (
          <li key={req.id}>
            {req.description}
            {req.mcr_reference && <> ({url
              ? <a href={url} target="_blank" rel="noopener noreferrer">{req.mcr_reference}</a>
              : req.mcr_reference})</>}
            {req.page_limit && <p className="req-detail">Page limit: {req.page_limit} pages</p>}
            {req.format_notes && <p className="req-detail">{req.format_notes}</p>}
            {req.local_rule_reference && <p className="req-detail">Local rule: {req.local_rule_reference}</p>}
          </li>
        );
      })}
    </ul>
  );
}

interface Props {
  courtId: number;
  selectedCaseTypeId: number | null;
  onSelect: (caseTypeId: number, caseTypeName: string) => void;
}

function CaseTypeSelector({ courtId, selectedCaseTypeId, onSelect }: Props) {
  const [caseTypes, setCaseTypes] = useState<CaseType[]>([]);
  const [requirementsResult, setRequirementsResult] = useState<{
    key: string; requirements?: FilingRequirement[]; error?: LoadFailure;
  }>();
  const [requirementsAttempt, setRequirementsAttempt] = useState(0);
  const requirementsKey = `${courtId}:${selectedCaseTypeId}:${requirementsAttempt}`;
  const currentRequirements = requirementsResult?.key === requirementsKey ? requirementsResult : undefined;
  const requirements = currentRequirements?.requirements ?? [];
  const [loading, setLoading] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [error, setError] = useState<LoadFailure | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    async function fetchCaseTypes() {
      setLoading(true);
      setError(null);
      try {
        const types = await getCaseTypes(courtId, false, controller.signal);
        if (controller.signal.aborted) return;
        setCaseTypes(types);
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(loadFailure(err, "We couldn't load case types for this court. Please retry."));
        setCaseTypes([]);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    fetchCaseTypes();
    return () => controller.abort();
  }, [courtId, reloadKey]);

  useEffect(() => {
    if (!selectedCaseTypeId) return;
    const controller = new AbortController();
    async function fetchRequirements() {
      try {
        const reqs = await getFilingRequirements(courtId, selectedCaseTypeId!, 'initial', controller.signal);
        if (!controller.signal.aborted) setRequirementsResult({ key: requirementsKey, requirements: reqs });
      } catch (err) {
        if (!controller.signal.aborted) setRequirementsResult({ key: requirementsKey,
          error: loadFailure(err, 'Could not load requirements for this case type. Please retry before continuing.') });
      }
    }
    fetchRequirements();
    return () => controller.abort();
  }, [courtId, selectedCaseTypeId, requirementsKey]);

  const categories = [...new Set(caseTypes.map(ct => ct.category))];

  const matchesFilters = (ct: CaseType) => (!categoryFilter || ct.category === categoryFilter)
    && (!searchQuery || ct.name.toLowerCase().includes(searchQuery.toLowerCase()));
  const noMatches = !caseTypes.some(matchesFilters);
  const listed = caseTypes.filter(ct => matchesFilters(ct) || ct.id === selectedCaseTypeId);

  const requiredDocs = requirements.filter(r => r.is_required);
  const optionalDocs = requirements.filter(r => !r.is_required);

  return (
    <div className="form-section">
      <h2>Choose a case type and review its requirements</h2>
      <p className="info-text">
        Choose the type of case for your filing. After selecting, review the filing
        requirements below to ensure you have all necessary documents.
      </p>

      <div className="filter-row">
        <div className="form-group">
          <label htmlFor="categoryFilter">Category</label>
          <select
            id="categoryFilter"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
          >
            <option value="">All categories</option>
            {categories.map(c => (
              <option key={c} value={c}>{c.replace(/_/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase())}</option>
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

      {loading && <p>Loading case types…</p>}
      {error && <LoadError failure={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      <fieldset className="case-type-list">
        <legend className="sr-only">Case type</legend>
        {listed.map((ct) => (
          <label key={ct.id} className={`case-type-option ${selectedCaseTypeId === ct.id ? 'selected' : ''}`}>
            <input
              type="radio"
              name="caseType"
              checked={selectedCaseTypeId === ct.id}
              onChange={() => onSelect(ct.id, ct.name)}
            />
            <span>{ct.name}</span>
            <span className={`case-type-fee ${ct.filing_fee_cents === 0 ? 'fee-free' : ''}`}>
              {formatFee(ct.filing_fee_cents)}
            </span>
            {ct.description && <span className="case-type-desc">{ct.description}</span>}
          </label>
        ))}
      </fieldset>
      {!loading && !error && noMatches && (
        <p className="no-results">No case types match your filters.</p>
      )}

      {selectedCaseTypeId && !currentRequirements && <p role="status">Loading filing requirements…</p>}
      {currentRequirements?.error && <LoadError failure={currentRequirements.error}
        onRetry={() => setRequirementsAttempt(attempt => attempt + 1)} />}
      {selectedCaseTypeId && requirements.length > 0 && (
        <div className="requirements-section">
          <h3>Filing requirements and court rules</h3>
          <p className="info-text">
            Review these requirements carefully. Missing required documents may cause the
            clerk to return your filing for correction.
          </p>

          {requiredDocs.length > 0 && <>
            <h4>Required documents ({requiredDocs.length})</h4>
            <RequirementList requirements={requiredDocs} />
          </>}
          {optionalDocs.length > 0 && <>
            <h4>Optional documents ({optionalDocs.length})</h4>
            <RequirementList requirements={optionalDocs} />
          </>}

          <h4>Michigan Court Rules</h4>
          <ul className="requirement-list">
            {COURT_RULE_LINKS.map(([href, label]) => (
              <li key={href}><a href={href} target="_blank" rel="noopener noreferrer">{label}</a></li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default CaseTypeSelector;
