import { useEffect, useState, useRef } from 'react';
import { getFilingRequirements } from '../../api/courts';
import { getFiling, uploadDocument, removeDocument } from '../../api/filings';
import { errorMessage, loadFailure, type LoadFailure } from '../../utils/errors';
import { FILING_CATEGORIES, getDocumentLabel } from '../../utils/documentTypes';
import { formatBytes } from '../../utils/format';
import LoadError from '../common/LoadError';

interface DocumentInfo {
  id: number;
  title: string;
  type: string;
  size: number;
  isSearchable: boolean;
}

interface Props {
  filingId: number;
  courtId: number;
  caseTypeId: number;
  filingType: string;
  documents: DocumentInfo[];
  onDocumentsChange: (docs: DocumentInfo[]) => void;
  onBusyChange: (busy: boolean) => void;
}

// Flatten for quick lookup
const ALL_TYPES = FILING_CATEGORIES.flatMap(cat => cat.types);
const COURT_CATEGORY = "Listed in this court's rules";

// MCR 2.119(A)(2): a motion presenting a question of law must be accompanied by a brief
//   (the brief may be combined with the motion).
// MCR 2.313(A): discovery motions require a meet-and-confer certification.
// A proposed order is NOT required at filing (MCR 2.602 governs entry of orders) — it is
//   recommended best practice, not a prerequisite.
const COMPANION_RULES: {
  trigger: string[];
  required: { code: string; label: string; rule: string }[];
  recommended: { code: string; label: string; rule: string }[];
}[] = [
  {
    // MCR 2.119(A)(2) calls for a brief on motions raising a question of law, but the
    // brief may be combined with the motion itself -- so it is recommended, not a blocker.
    trigger: [
      'MOT_SD', 'MOT_DISMISS', 'MOT_COMPEL', 'MOT_PROTECTIVE', 'MOT_SANCTIONS',
      'MOT_DEFAULT', 'MOT_SJ', 'MOT_LIMINE', 'MOT_RECONSIDER', 'MOT_RELIEF',
      'MOT_STAY', 'MOT_ADJOURN', 'MOT_INTERVENE', 'MOT_AMEND', 'MOT_QUASH',
      'MOT_TRANSFER', 'MOT_CONSOLIDATE', 'MOT_WITHDRAW', 'MOT_TRO',
      'MOT_PRELIM_INJ', 'MOT_FEES', 'MOT_OTHER',
    ],
    required: [],
    recommended: [
      { code: 'BRIEF_SUPPORT', label: getDocumentLabel('BRIEF_SUPPORT'), rule: 'MCR 2.119(A)(2)' },
      { code: 'PROPOSED_ORDER', label: getDocumentLabel('PROPOSED_ORDER'), rule: 'MCR 2.602' },
      { code: 'NOT_HEARING', label: getDocumentLabel('NOT_HEARING'), rule: 'MCR 2.119(C)' },
      { code: 'POS_ELECTRONIC', label: getDocumentLabel('POS_ELECTRONIC'), rule: 'MCR 1.109(G)(6)' },
    ],
  },
  {
    // Discovery motions: a good-faith effort to resolve is a factor in awarding motion
    // expenses (MCR 2.313(A)(5)) -- a certification is recommended best practice, not a
    // required filing. (A non-party motion to compel must include the subpoena + proof of
    // service, MCR 2.313(A)(2)(c).)
    trigger: ['MOT_COMPEL', 'MOT_PROTECTIVE', 'MOT_SANCTIONS'],
    required: [],
    recommended: [
      { code: 'DISC_CERT_GF', label: getDocumentLabel('DISC_CERT_GF'), rule: 'MCR 2.313(A)(5)' },
    ],
  },
  {
    // Summary disposition motions benefit from affidavits
    trigger: ['MOT_SD', 'MOT_SJ'],
    required: [],
    recommended: [
      { code: 'AFFIDAVIT', label: 'Supporting Affidavits', rule: 'MCR 2.116(G)(4)' },
    ],
  },
  {
    // Default judgment motions
    trigger: ['MOT_DEFAULT'],
    required: [
      { code: 'AFF_DEFAULT', label: getDocumentLabel('AFF_DEFAULT'), rule: 'MCR 2.603(A)' },
    ],
    recommended: [],
  },
  {
    // TRO/Preliminary injunction
    trigger: ['MOT_TRO', 'MOT_PRELIM_INJ'],
    required: [
      { code: 'AFFIDAVIT', label: 'Verified Complaint or Affidavit', rule: 'MCR 3.310(B)' },
    ],
    recommended: [],
  },
];

function getCompanionRequirements(uploadedTypeCodes: string[]) {
  const required: { code: string; label: string; rule: string }[] = [];
  const recommended: { code: string; label: string; rule: string }[] = [];
  const seenRequired = new Set<string>();
  const seenRecommended = new Set<string>();

  for (const rule of COMPANION_RULES) {
    const triggered = rule.trigger.some(t => uploadedTypeCodes.includes(t));
    if (!triggered) continue;

    for (const r of rule.required) {
      if (!seenRequired.has(r.code) && !uploadedTypeCodes.includes(r.code)) {
        required.push(r);
        seenRequired.add(r.code);
      }
    }
    for (const r of rule.recommended) {
      if (!seenRecommended.has(r.code) && !uploadedTypeCodes.includes(r.code) && !seenRequired.has(r.code)) {
        recommended.push(r);
        seenRecommended.add(r.code);
      }
    }
  }
  return { required, recommended };
}

function DocumentUpload({
  filingId,
  courtId,
  caseTypeId,
  filingType,
  documents,
  onDocumentsChange,
  onBusyChange,
}: Props) {
  const [pendingAction, setPendingAction] = useState<'upload' | 'remove' | null>(null);
  const busy = pendingAction !== null;
  const uploadRequest = useRef<{ file: File; metadata: string; key: string }>();
  const [selectedCategory, setSelectedCategory] = useState('');
  const [docType, setDocType] = useState('');
  const [docTitle, setDocTitle] = useState('');
  // The title this form last filled in from a type; a different title is the filer's own.
  const autoFilledTitle = useRef('');
  const [isConfidential, setIsConfidential] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { required, recommended } = getCompanionRequirements(documents.map(doc => doc.type));
  // Validation matches the court's exact document codes; offer any the catalog lacks.
  const [courtTypes, setCourtTypes] = useState<typeof ALL_TYPES>([]);
  const [requirementsFailed, setRequirementsFailed] = useState<LoadFailure | null>(null);
  const [requirementsAttempt, setRequirementsAttempt] = useState(0);
  const allTypes = [...courtTypes, ...ALL_TYPES];

  useEffect(() => {
    if (filingType === 'service_only') return;
    const controller = new AbortController();
    getFilingRequirements(courtId, caseTypeId, filingType, controller.signal).then((requirements) => {
      setRequirementsFailed(null);
      setCourtTypes(requirements
        .filter(r => !ALL_TYPES.some(t => t.code === r.document_type_code))
        .map(r => ({ code: r.document_type_code, label: r.description, mcr: r.mcr_reference ?? '' })));
    }).catch((err) => {
      if (!controller.signal.aborted) {
        setRequirementsFailed(loadFailure(err, "Could not load the document types in this court's rules. Retry before choosing a type."));
      }
    });
    return () => controller.abort();
  }, [courtId, caseTypeId, filingType, requirementsAttempt]);

  function selectCompanion(code: string, label: string) {
    setSelectedCategory('');
    setDocType(code);
    autoFilledTitle.current = label;
    setDocTitle(label);
    fileInputRef.current?.focus();
  }

  const filteredTypes = selectedCategory === COURT_CATEGORY
    ? courtTypes
    : FILING_CATEGORIES.find(c => c.label === selectedCategory)?.types || [];

  // Auto-fill the title from the type, and keep following the type until the filer edits it.
  const handleDocTypeChange = (code: string) => {
    setDocType(code);
    const typeInfo = allTypes.find(t => t.code === code);
    if (typeInfo && (!docTitle || docTitle === autoFilledTitle.current)) {
      autoFilledTitle.current = typeInfo.label;
      setDocTitle(typeInfo.label);
    }
  };

  const refreshDocuments = async () => {
    const saved = await getFiling(filingId);
    onDocumentsChange(saved.documents.map(doc => ({
      id: doc.id, title: doc.title, type: doc.document_type_code,
      size: doc.file_size_bytes, isSearchable: doc.is_text_searchable,
    })));
  };

  const handleUpload = async () => {
    const file = fileInputRef.current?.files?.[0];
    if (!file) {
      setError('Please select a file');
      return;
    }
    if (!docType) {
      setError('Please select a document type');
      return;
    }
    if (!docTitle.trim()) {
      setError('Please enter a document title');
      return;
    }

    const metadata = JSON.stringify([filingId, docType, docTitle, isConfidential]);
    if (uploadRequest.current?.file !== file || uploadRequest.current.metadata !== metadata) {
      uploadRequest.current = { file, metadata, key: crypto.randomUUID() };
    }
    setPendingAction('upload');
    onBusyChange(true);
    setError(null);
    setWarnings([]);

    try {
      const result = await uploadDocument(
        filingId, file, docType, docTitle, uploadRequest.current.key, isConfidential,
      );
      await refreshDocuments();
      uploadRequest.current = undefined;
      setWarnings(result.warnings ?? []);
      autoFilledTitle.current = '';
      setDocTitle('');
      setDocType('');
      setIsConfidential(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err: unknown) {
      // Surface the backend detail (e.g. malware 422 "Rejected: ...", unsupported-type 415).
      setError(errorMessage(err, 'Could not confirm the upload. Retry with the same file, or refresh this filing to check its saved documents.'));
    } finally {
      setPendingAction(null);
      onBusyChange(false);
    }
  };

  const handleRemove = async (docId: number) => {
    setPendingAction('remove');
    onBusyChange(true);
    setError(null);
    try {
      await removeDocument(filingId, docId);
      await refreshDocuments();
    } catch (err) {
      setError(errorMessage(err, 'Could not confirm removal. Refresh the filing before retrying.'));
    } finally {
      setPendingAction(null);
      onBusyChange(false);
    }
  };

  const getTypeLabel = (code: string) => {
    return courtTypes.find(t => t.code === code)?.label || getDocumentLabel(code);
  };

  const getTypeMcr = (code: string) => {
    return allTypes.find(t => t.code === code)?.mcr || '';
  };

  return (
    <div className="form-section">
      <h2>Upload Documents</h2>
      <p className="info-text">
        Select the document type, upload your file, and add it to the filing.
        All PDFs must be text-searchable per MCR 1.109. Maximum file size: 100MB.
      </p>

      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {requirementsFailed && <LoadError
        failure={requirementsFailed}
        onRetry={() => setRequirementsAttempt(attempt => attempt + 1)} />}

      {warnings.length > 0 && (
        <div className="alert alert-warning" role="status">
          <strong>Possible PII detected (MCR 1.109)</strong> — review and redact before submitting.
          <ul className="pii-warning-list">
            {warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}

      {/* Upload Form */}
      <div className="upload-form">
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="docCategory">Category</label>
            <select
              id="docCategory"
              disabled={busy}
              value={selectedCategory}
              onChange={(e) => { setSelectedCategory(e.target.value); setDocType(''); }}
            >
              <option value="">All Categories</option>
              {courtTypes.length > 0 && <option value={COURT_CATEGORY}>{COURT_CATEGORY}</option>}
              {FILING_CATEGORIES.map((cat) => (
                <option key={cat.label} value={cat.label}>{cat.label}</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="docType">
              Document Type <span className="required-marker">*</span>
            </label>
            <select
              id="docType"
              disabled={busy}
              value={docType}
              onChange={(e) => handleDocTypeChange(e.target.value)}
            >
              <option value="">-- Select document type --</option>
              {selectedCategory ? (
                filteredTypes.map((dt) => (
                  <option key={dt.code} value={dt.code}>
                    {dt.label}{dt.mcr ? ` (${dt.mcr})` : ''}
                  </option>
                ))
              ) : (
                [{ label: COURT_CATEGORY, types: courtTypes }, ...FILING_CATEGORIES]
                  .filter(cat => cat.types.length > 0).map((cat) => (
                  <optgroup key={cat.label} label={cat.label}>
                    {cat.types.map((dt) => (
                      <option key={dt.code} value={dt.code}>
                        {dt.label}{dt.mcr ? ` (${dt.mcr})` : ''}
                      </option>
                    ))}
                  </optgroup>
                ))
              )}
            </select>
          </div>
        </div>

        {docType && getTypeMcr(docType) && (
          <div className="doc-type-mcr-hint">
            Court Rule: <strong>{getTypeMcr(docType)}</strong>
          </div>
        )}

        <div className="form-group">
          <label htmlFor="docTitle">
            Document Title <span className="required-marker">*</span>
          </label>
          <input
            id="docTitle"
              disabled={busy}
            type="text"
            value={docTitle}
            onChange={(e) => setDocTitle(e.target.value)}
            placeholder="e.g., Answer to the complaint"
          />
        </div>
        <div className="form-group">
          <label htmlFor="docFile">
            File <span className="required-marker">*</span>
          </label>
          <input
            id="docFile"
              disabled={busy}
            type="file"
            ref={fileInputRef}
            accept=".pdf,.doc,.docx,.txt,.rtf,.tiff,.tif,.jpg,.jpeg,.png"
          />
          <span className="field-hint">Accepted: PDF (preferred), Word, TXT, RTF, TIFF, JPG, PNG &middot; Max 100 MB per file</span>
        </div>
        <div className="form-group checkbox">
          <label>
            <input
              type="checkbox"
              checked={docType === 'FEE_WAIVER' || isConfidential}
              disabled={busy || docType === 'FEE_WAIVER'}
              onChange={(e) => setIsConfidential(e.target.checked)}
            />
            {docType === 'FEE_WAIVER' ? 'Fee waiver request — nonpublic' : 'Mark as confidential (not public)'}
          </label>
        </div>
        <button
          className="btn btn-primary"
          onClick={handleUpload}
          disabled={busy || !docType}
        >
          {pendingAction === 'upload' ? 'Uploading...' : 'Upload Document'}
        </button>
      </div>

      {/* Uploaded Documents List */}
      {documents.length > 0 && (
        <div className="uploaded-documents">
          <h3>Documents in This Filing ({documents.length})</h3>
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>MCR</th>
                <th>Size</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id}>
                  <td>{doc.title}</td>
                  <td>{getTypeLabel(doc.type)}</td>
                  <td><span className="mcr-ref">{getTypeMcr(doc.type)}</span></td>
                  <td>{formatBytes(doc.size)}</td>
                  <td>
                    <button
                      className="btn btn-small btn-danger"
                      onClick={() => handleRemove(doc.id)}
                      disabled={busy}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* MCR Companion Document Requirements */}
      {(required.length > 0 || recommended.length > 0) && (
        <div className="companion-requirements">
          {required.length > 0 && (
            <div className="alert alert-error">
              <strong>Required companion documents (Michigan Court Rules):</strong>
              <ul>
                {required.map(r => (
                  <li key={r.code}>
                    <strong>{r.label}</strong> &mdash; {r.rule}
                    {' '}<button type="button" className="btn btn-small btn-secondary" disabled={busy}
                      onClick={() => selectCompanion(r.code, r.label)}>Add {r.label}</button>
                    {r.code === 'BRIEF_SUPPORT' && (
                      <span className="companion-hint"> (may be combined with the motion as a single document)</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {recommended.length > 0 && (
            <div className="alert alert-info">
              <strong>Recommended:</strong>
              <ul>
                {recommended.map(r => (
                  <li key={r.code}>
                    {r.label} &mdash; {r.rule}
                    {' '}<button type="button" className="btn btn-small btn-secondary" disabled={busy}
                      onClick={() => selectCompanion(r.code, r.label)}>Add {r.label}</button>
                    {r.code === 'BRIEF_SUPPORT' && (
                      <span className="companion-hint"> (may be combined with the motion as a single document, so a separate brief is not required to file)</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default DocumentUpload;
