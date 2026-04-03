import { useState, useRef } from 'react';
import { uploadDocument, removeDocument } from '../../api/filings';

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
  documents: DocumentInfo[];
  onDocumentsChange: (docs: DocumentInfo[]) => void;
}

// Comprehensive MCR-based filing types organized by category
const FILING_CATEGORIES = [
  {
    label: 'Initiating Documents',
    types: [
      { code: 'COMPLAINT', label: 'Complaint', mcr: 'MCR 2.111' },
      { code: 'PETITION', label: 'Petition', mcr: 'MCR 3.206' },
      { code: 'COUNTERCLAIM', label: 'Counterclaim', mcr: 'MCR 2.203(A)' },
      { code: 'CROSSCLAIM', label: 'Cross-Claim', mcr: 'MCR 2.203(B)' },
      { code: 'THIRD_PARTY', label: 'Third-Party Complaint', mcr: 'MCR 2.204' },
      { code: 'INTERVENOR', label: 'Complaint in Intervention', mcr: 'MCR 2.209' },
      { code: 'SUMMONS', label: 'Summons', mcr: 'MCR 2.102' },
      { code: 'AMENDED_COMP', label: 'Amended Complaint', mcr: 'MCR 2.118' },
    ],
  },
  {
    label: 'Responsive Pleadings',
    types: [
      { code: 'ANSWER', label: 'Answer & Affirmative Defenses', mcr: 'MCR 2.111(F)' },
      { code: 'REPLY', label: 'Reply to Counterclaim', mcr: 'MCR 2.110(B)' },
      { code: 'RESPONSE', label: 'Response to Motion', mcr: 'MCR 2.119(A)(2)' },
      { code: 'REPLY_BRIEF', label: 'Reply Brief', mcr: 'MCR 2.119(A)(2)' },
      { code: 'OBJECTION', label: 'Objection', mcr: '' },
    ],
  },
  {
    label: 'Motions',
    types: [
      { code: 'MOT_SD', label: 'Motion for Summary Disposition', mcr: 'MCR 2.116' },
      { code: 'MOT_DISMISS', label: 'Motion to Dismiss', mcr: 'MCR 2.116(C)' },
      { code: 'MOT_COMPEL', label: 'Motion to Compel Discovery', mcr: 'MCR 2.313(A)' },
      { code: 'MOT_PROTECTIVE', label: 'Motion for Protective Order', mcr: 'MCR 2.302(C)' },
      { code: 'MOT_SANCTIONS', label: 'Motion for Sanctions', mcr: 'MCR 2.114(E)' },
      { code: 'MOT_DEFAULT', label: 'Motion for Default Judgment', mcr: 'MCR 2.603' },
      { code: 'MOT_SJ', label: 'Motion for Summary Judgment', mcr: 'MCR 2.116(C)(10)' },
      { code: 'MOT_LIMINE', label: 'Motion in Limine', mcr: 'MRE 103' },
      { code: 'MOT_RECONSIDER', label: 'Motion for Reconsideration', mcr: 'MCR 2.119(F)' },
      { code: 'MOT_RELIEF', label: 'Motion for Relief from Judgment', mcr: 'MCR 2.612' },
      { code: 'MOT_STAY', label: 'Motion to Stay Proceedings', mcr: 'MCR 2.614' },
      { code: 'MOT_ADJOURN', label: 'Motion to Adjourn', mcr: 'MCR 2.503' },
      { code: 'MOT_INTERVENE', label: 'Motion to Intervene', mcr: 'MCR 2.209' },
      { code: 'MOT_AMEND', label: 'Motion to Amend Pleadings', mcr: 'MCR 2.118' },
      { code: 'MOT_QUASH', label: 'Motion to Quash Subpoena', mcr: 'MCR 2.506(H)' },
      { code: 'MOT_TRANSFER', label: 'Motion to Transfer Venue', mcr: 'MCR 2.222' },
      { code: 'MOT_CONSOLIDATE', label: 'Motion to Consolidate', mcr: 'MCR 2.505(A)' },
      { code: 'MOT_WITHDRAW', label: 'Motion to Withdraw as Attorney', mcr: 'MCR 2.117(C)' },
      { code: 'MOT_TRO', label: 'Motion for Temporary Restraining Order', mcr: 'MCR 3.310' },
      { code: 'MOT_PRELIM_INJ', label: 'Motion for Preliminary Injunction', mcr: 'MCR 3.310' },
      { code: 'MOT_FEES', label: 'Motion for Attorney Fees/Costs', mcr: 'MCR 2.403(O)' },
      { code: 'MOT_OTHER', label: 'Other Motion', mcr: 'MCR 2.119' },
    ],
  },
  {
    label: 'Discovery',
    types: [
      { code: 'DISC_INTERROG', label: 'Interrogatories', mcr: 'MCR 2.309' },
      { code: 'DISC_ANSWERS', label: 'Answers to Interrogatories', mcr: 'MCR 2.309(B)' },
      { code: 'DISC_RFP', label: 'Request for Production of Documents', mcr: 'MCR 2.310' },
      { code: 'DISC_RFP_RESP', label: 'Response to Request for Production', mcr: 'MCR 2.310(B)' },
      { code: 'DISC_RFA', label: 'Request for Admissions', mcr: 'MCR 2.312' },
      { code: 'DISC_RFA_RESP', label: 'Response to Request for Admissions', mcr: 'MCR 2.312(B)' },
      { code: 'DISC_DEPO_NOT', label: 'Notice of Deposition', mcr: 'MCR 2.306' },
      { code: 'DISC_DEPO_TR', label: 'Deposition Transcript', mcr: 'MCR 2.306' },
      { code: 'DISC_SUBPOENA', label: 'Subpoena / Subpoena Duces Tecum', mcr: 'MCR 2.506' },
      { code: 'DISC_DOM_SUBP', label: 'Domesticating Out-of-State Subpoena', mcr: 'MCL 600.2163a' },
      { code: 'DISC_IME', label: 'Request for Independent Medical Exam', mcr: 'MCR 2.311' },
      { code: 'DISC_INITIAL', label: 'Initial Disclosure', mcr: 'MCR 2.302(A)' },
      { code: 'DISC_SUPPL', label: 'Supplemental Disclosure', mcr: 'MCR 2.302(A)' },
      { code: 'DISC_PRIVILEGE', label: 'Privilege Log', mcr: 'MCR 2.302(C)(2)' },
      { code: 'DISC_EXPERT', label: 'Expert Witness Identification & Opinions', mcr: 'MCR 2.302(B)(4)' },
      { code: 'DISC_CERT_GF', label: 'Certification of Good Faith Discovery Effort', mcr: 'MCR 2.313(A)' },
    ],
  },
  {
    label: 'Briefs & Memoranda',
    types: [
      { code: 'BRIEF_SUPPORT', label: 'Brief in Support of Motion', mcr: 'MCR 2.119(A)(2)' },
      { code: 'BRIEF_RESPONSE', label: 'Response Brief', mcr: 'MCR 2.119(A)(2)' },
      { code: 'BRIEF_REPLY', label: 'Reply Brief', mcr: 'MCR 2.119(A)(2)' },
      { code: 'BRIEF_AMICUS', label: 'Amicus Curiae Brief', mcr: 'MCR 7.212(H)' },
      { code: 'MEMO_LAW', label: 'Memorandum of Law', mcr: '' },
      { code: 'TRIAL_BRIEF', label: 'Trial Brief', mcr: '' },
    ],
  },
  {
    label: 'Orders & Judgments',
    types: [
      { code: 'PROPOSED_ORDER', label: 'Proposed Order', mcr: 'MCR 2.602' },
      { code: 'STIP_ORDER', label: 'Stipulated Order', mcr: 'MCR 2.507' },
      { code: 'CONSENT_JUDG', label: 'Consent Judgment', mcr: 'MCR 2.507' },
      { code: 'DEFAULT_JUDG', label: 'Default Judgment', mcr: 'MCR 2.603' },
      { code: 'PROPOSED_JUDG', label: 'Proposed Judgment', mcr: 'MCR 2.602' },
      { code: 'SATISFACTION', label: 'Satisfaction of Judgment', mcr: '' },
    ],
  },
  {
    label: 'Post-Judgment',
    types: [
      { code: 'PJ_NEW_TRIAL', label: 'Motion for New Trial', mcr: 'MCR 2.606' },
      { code: 'PJ_SET_ASIDE', label: 'Motion to Set Aside Default Judgment', mcr: 'MCR 2.603' },
      { code: 'PJ_GARNISH', label: 'Writ of Garnishment', mcr: 'MCL 600.4011' },
      { code: 'PJ_EXECUTION', label: 'Writ of Execution', mcr: 'MCR 3.106' },
      { code: 'PJ_DEBTOR_EXAM', label: 'Order for Judgment Debtor Examination', mcr: 'MCR 2.621' },
      { code: 'PJ_ABSTRACT', label: 'Abstract of Judgment', mcr: '' },
    ],
  },
  {
    label: 'ADR / Settlement',
    types: [
      { code: 'ADR_CASE_EVAL', label: 'Case Evaluation Summary', mcr: 'MCR 2.403' },
      { code: 'ADR_ACCEPT_REJ', label: 'Accept/Reject Case Evaluation', mcr: 'MCR 2.403(L)' },
      { code: 'ADR_MEDIATION', label: 'Mediation Summary', mcr: 'MCR 2.411' },
      { code: 'ADR_OFFER_JUDG', label: 'Offer of Judgment', mcr: 'MCR 2.405' },
      { code: 'ADR_ACCEPT_OJ', label: 'Acceptance of Offer of Judgment', mcr: 'MCR 2.405' },
      { code: 'ADR_SETTLE', label: 'Settlement Agreement', mcr: '' },
      { code: 'ADR_STIP_DISM', label: 'Stipulation and Order of Dismissal', mcr: 'MCR 2.504' },
    ],
  },
  {
    label: 'Notices',
    types: [
      { code: 'NOT_HEARING', label: 'Notice of Hearing', mcr: 'MCR 2.119(C)' },
      { code: 'NOT_DEPO', label: 'Notice of Deposition', mcr: 'MCR 2.306(B)' },
      { code: 'NOT_APPEAR', label: 'Notice of Appearance', mcr: 'MCR 2.117(A)' },
      { code: 'NOT_APPEN_ISS', label: 'Notice of Appeal', mcr: 'MCR 7.204' },
      { code: 'NOT_DISMISS', label: 'Notice of Voluntary Dismissal', mcr: 'MCR 2.504(A)' },
      { code: 'NOT_SETTLEMENT', label: 'Notice of Settlement', mcr: '' },
      { code: 'NOT_NONPARTY', label: 'Notice to Non-Party', mcr: '' },
      { code: 'NOT_CHANGE_ADDR', label: 'Notice of Change of Address', mcr: 'MCR 2.107(G)' },
    ],
  },
  {
    label: 'Affidavits & Declarations',
    types: [
      { code: 'AFFIDAVIT', label: 'Affidavit', mcr: '' },
      { code: 'AFF_MERIT', label: 'Affidavit of Merit (Medical Malpractice)', mcr: 'MCL 600.2912d' },
      { code: 'AFF_SERVICE', label: 'Affidavit of Service', mcr: 'MCR 2.104' },
      { code: 'AFF_DEFAULT', label: 'Affidavit of Default', mcr: 'MCR 2.603(A)' },
      { code: 'AFF_COSTS', label: 'Affidavit of Costs', mcr: '' },
      { code: 'DECLARATION', label: 'Declaration Under Penalty of Perjury', mcr: 'MCR 1.109(D)(3)' },
      { code: 'VERIFICATION', label: 'Verification', mcr: 'MCR 1.109(D)(3)' },
    ],
  },
  {
    label: 'Proof of Service',
    types: [
      { code: 'POS_PERSONAL', label: 'Proof of Service - Personal', mcr: 'MCR 2.104' },
      { code: 'POS_MAIL', label: 'Proof of Service - Mail', mcr: 'MCR 2.107' },
      { code: 'POS_ELECTRONIC', label: 'Proof of Service - Electronic', mcr: 'MCR 1.109(G)(6)' },
    ],
  },
  {
    label: 'Family Law',
    types: [
      { code: 'FAM_DIVORCE', label: 'Complaint for Divorce', mcr: 'MCR 3.206' },
      { code: 'FAM_CUSTODY', label: 'Custody Motion/Petition', mcr: 'MCL 722.27' },
      { code: 'FAM_SUPPORT', label: 'Motion to Modify Child Support', mcr: 'MCL 552.517' },
      { code: 'FAM_PPO', label: 'Petition for Personal Protection Order', mcr: 'MCR 3.703' },
      { code: 'FAM_FOC', label: 'Friend of the Court Recommendation', mcr: 'MCL 552.507' },
      { code: 'FAM_PARENTING', label: 'Proposed Parenting Time Order', mcr: 'MCL 722.27a' },
      { code: 'FAM_SETTLE', label: 'Marital Settlement Agreement', mcr: '' },
      { code: 'FAM_UCCJEA', label: 'UCCJEA Affidavit', mcr: 'MCL 722.1209' },
      { code: 'FAM_FINANCIAL', label: 'Verified Financial Information Form (CC 320)', mcr: 'MCR 3.206' },
      { code: 'FAM_SEP_MAINT', label: 'Complaint for Separate Maintenance', mcr: 'MCR 3.201' },
      { code: 'FAM_ANNUL', label: 'Complaint for Annulment', mcr: 'MCR 3.201' },
      { code: 'FAM_PATERNITY', label: 'Petition for Paternity', mcr: 'MCR 3.201' },
      { code: 'FAM_QDRO', label: 'Qualified Domestic Relations Order (QDRO)', mcr: '' },
      { code: 'FAM_SPOUSAL', label: 'Motion to Modify Spousal Support', mcr: '' },
    ],
  },
  {
    label: 'Appellate',
    types: [
      { code: 'APP_NOTICE', label: 'Claim of Appeal', mcr: 'MCR 7.204' },
      { code: 'APP_LEAVE', label: 'Application for Leave to Appeal', mcr: 'MCR 7.205' },
      { code: 'APP_BRIEF', label: "Appellant's Brief", mcr: 'MCR 7.212' },
      { code: 'APP_RESP', label: "Appellee's Brief", mcr: 'MCR 7.212' },
      { code: 'APP_REPLY', label: 'Reply Brief on Appeal', mcr: 'MCR 7.212' },
      { code: 'APP_RECORD', label: 'Record on Appeal', mcr: 'MCR 7.210' },
      { code: 'APP_EMERGENCY', label: 'Emergency Application', mcr: 'MCR 7.211(C)(6)' },
      { code: 'APP_TRANSCRIPT', label: 'Transcript Order / Filing', mcr: 'MCR 7.210(B)' },
    ],
  },
  {
    label: 'Case Administration',
    types: [
      { code: 'COVER_SHEET', label: 'Civil Case Cover Sheet', mcr: 'MCR 8.119' },
      { code: 'STIPULATION', label: 'Stipulation', mcr: 'MCR 2.507' },
      { code: 'CASE_EVAL', label: 'Case Evaluation Summary', mcr: 'MCR 2.403' },
      { code: 'MEDIATION', label: 'Mediation Summary', mcr: 'MCR 2.411' },
      { code: 'PRETRIAL_STMT', label: 'Pretrial Statement', mcr: 'MCR 2.401' },
      { code: 'WITNESS_LIST', label: 'Witness List', mcr: 'MCR 2.401(I)' },
      { code: 'EXHIBIT_LIST', label: 'Exhibit List', mcr: 'MCR 2.401(I)' },
      { code: 'JURY_INSTRUCT', label: 'Proposed Jury Instructions', mcr: 'MCR 2.512(D)' },
      { code: 'VERDICT_FORM', label: 'Proposed Verdict Form', mcr: 'MCR 2.514' },
      { code: 'FEE_WAIVER', label: 'Fee Waiver Request', mcr: 'MCR 2.002' },
      { code: 'APPEARANCE', label: 'Notice of Appearance', mcr: 'MCR 2.117(A)' },
      { code: 'SCHED_ORDER', label: 'Scheduling Order', mcr: 'MCR 2.401' },
      { code: 'LIS_PENDENS', label: 'Lis Pendens (Notice of Pending Litigation)', mcr: 'MCL 565.25' },
    ],
  },
  {
    label: 'Exhibits & Supporting Documents',
    types: [
      { code: 'EXHIBIT', label: 'Exhibit', mcr: '' },
      { code: 'ATTACHMENT', label: 'Attachment', mcr: '' },
      { code: 'CORRESPONDENCE', label: 'Correspondence / Letter', mcr: '' },
      { code: 'TRANSCRIPT', label: 'Transcript', mcr: '' },
      { code: 'EXPERT_REPORT', label: 'Expert Report / Opinion', mcr: 'MCR 2.302(B)(4)' },
    ],
  },
  {
    label: 'Other',
    types: [
      { code: 'OTHER', label: 'Other Document', mcr: '' },
    ],
  },
];

// Flatten for quick lookup
const ALL_TYPES = FILING_CATEGORIES.flatMap(cat => cat.types);

// MCR 2.119(A)(2): All motions must be accompanied by a brief (or combined motion+brief).
// MCR 2.313(A): Discovery motions require a meet-and-confer certification.
// MCR 2.119(A)(2): All motions must include a proposed order.
const COMPANION_RULES: {
  trigger: string[];
  required: { code: string; label: string; rule: string }[];
  recommended: { code: string; label: string; rule: string }[];
}[] = [
  {
    // All motions require a brief per MCR 2.119(A)(2)
    trigger: [
      'MOT_SD', 'MOT_DISMISS', 'MOT_COMPEL', 'MOT_PROTECTIVE', 'MOT_SANCTIONS',
      'MOT_DEFAULT', 'MOT_SJ', 'MOT_LIMINE', 'MOT_RECONSIDER', 'MOT_RELIEF',
      'MOT_STAY', 'MOT_ADJOURN', 'MOT_INTERVENE', 'MOT_AMEND', 'MOT_QUASH',
      'MOT_TRANSFER', 'MOT_CONSOLIDATE', 'MOT_WITHDRAW', 'MOT_TRO',
      'MOT_PRELIM_INJ', 'MOT_FEES', 'MOT_OTHER',
    ],
    required: [
      { code: 'BRIEF_SUPPORT', label: 'Brief in Support of Motion', rule: 'MCR 2.119(A)(2)' },
      { code: 'PROPOSED_ORDER', label: 'Proposed Order', rule: 'MCR 2.119(A)(2)' },
    ],
    recommended: [
      { code: 'NOT_HEARING', label: 'Notice of Hearing', rule: 'MCR 2.119(C)' },
      { code: 'POS_ELECTRONIC', label: 'Proof of Service', rule: 'MCR 1.109(G)(6)' },
    ],
  },
  {
    // Discovery motions also require meet-and-confer certification
    trigger: ['MOT_COMPEL', 'MOT_PROTECTIVE', 'MOT_SANCTIONS'],
    required: [
      { code: 'DISC_CERT_GF', label: 'Certification of Good Faith Discovery Effort', rule: 'MCR 2.313(A)' },
    ],
    recommended: [],
  },
  {
    // Summary disposition motions benefit from affidavits
    trigger: ['MOT_SD', 'MOT_SJ'],
    required: [],
    recommended: [
      { code: 'AFFIDAVIT', label: 'Supporting Affidavit(s)', rule: 'MCR 2.116(G)(4)' },
    ],
  },
  {
    // Default judgment motions
    trigger: ['MOT_DEFAULT'],
    required: [
      { code: 'AFF_DEFAULT', label: 'Affidavit of Default', rule: 'MCR 2.603(A)' },
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
  courtId: _courtId,
  caseTypeId: _caseTypeId,
  documents,
  onDocumentsChange,
}: Props) {
  const [uploading, setUploading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState('');
  const [docType, setDocType] = useState('');
  const [docTitle, setDocTitle] = useState('');
  const [isConfidential, setIsConfidential] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const filteredTypes = selectedCategory
    ? FILING_CATEGORIES.find(c => c.label === selectedCategory)?.types || []
    : ALL_TYPES;

  // Auto-fill title when document type is selected
  const handleDocTypeChange = (code: string) => {
    setDocType(code);
    const typeInfo = ALL_TYPES.find(t => t.code === code);
    if (typeInfo && !docTitle) {
      setDocTitle(typeInfo.label);
    }
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

    setUploading(true);
    setError(null);

    try {
      const result = await uploadDocument(filingId, file, docType, docTitle, isConfidential);
      onDocumentsChange([
        ...documents,
        {
          id: result.id,
          title: result.title,
          type: docType,
          size: result.file_size_bytes,
          isSearchable: result.is_text_searchable ?? false,
        },
      ]);
      setDocTitle('');
      setDocType('');
      setIsConfidential(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Upload failed';
      setError(message);
    } finally {
      setUploading(false);
    }
  };

  const handleRemove = async (docId: number) => {
    try {
      await removeDocument(filingId, docId);
      onDocumentsChange(documents.filter((d) => d.id !== docId));
    } catch {
      setError('Failed to remove document');
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  };

  const getTypeLabel = (code: string) => {
    return ALL_TYPES.find(t => t.code === code)?.label || code;
  };

  const getTypeMcr = (code: string) => {
    return ALL_TYPES.find(t => t.code === code)?.mcr || '';
  };

  return (
    <div className="form-section">
      <h3>Upload Documents</h3>
      <p className="info-text">
        Select the document type, upload your file, and add it to the filing.
        All PDFs must be text-searchable per MCR 1.109. Maximum file size: 100MB.
      </p>

      {error && <div className="alert alert-error">{error}</div>}

      {/* Upload Form */}
      <div className="upload-form">
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="docCategory">Category</label>
            <select
              id="docCategory"
              value={selectedCategory}
              onChange={(e) => { setSelectedCategory(e.target.value); setDocType(''); }}
            >
              <option value="">All Categories</option>
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
                FILING_CATEGORIES.map((cat) => (
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
            type="text"
            value={docTitle}
            onChange={(e) => setDocTitle(e.target.value)}
            placeholder="e.g., Motion for Summary Disposition"
          />
        </div>
        <div className="form-group">
          <label htmlFor="docFile">
            File <span className="required-marker">*</span>
          </label>
          <input
            id="docFile"
            type="file"
            ref={fileInputRef}
            accept=".pdf,.doc,.docx,.txt,.rtf,.tiff,.tif,.jpg,.jpeg,.png"
          />
          <span className="field-hint">Accepted: PDF (preferred), Word, TXT, RTF, TIFF, JPG, PNG</span>
        </div>
        <div className="form-group checkbox">
          <label>
            <input
              type="checkbox"
              checked={isConfidential}
              onChange={(e) => setIsConfidential(e.target.checked)}
            />
            Mark as confidential (sealed from public access)
          </label>
        </div>
        <button
          className="btn btn-primary"
          onClick={handleUpload}
          disabled={uploading || !docType}
        >
          {uploading ? 'Uploading...' : 'Upload Document'}
        </button>
      </div>

      {/* Uploaded Documents List */}
      {documents.length > 0 && (
        <div className="uploaded-documents">
          <h4>Documents in This Filing ({documents.length})</h4>
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
                  <td>{formatSize(doc.size)}</td>
                  <td>
                    <button
                      className="btn btn-small btn-danger"
                      onClick={() => handleRemove(doc.id)}
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
      {documents.length > 0 && (() => {
        const uploadedCodes = documents.map(d => d.type);
        const { required, recommended } = getCompanionRequirements(uploadedCodes);
        if (required.length === 0 && recommended.length === 0) return null;
        return (
          <div className="companion-requirements">
            {required.length > 0 && (
              <div className="alert alert-error">
                <strong>Required companion documents (Michigan Court Rules):</strong>
                <ul>
                  {required.map(r => (
                    <li key={r.code}>
                      <strong>{r.label}</strong> &mdash; {r.rule}
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
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        );
      })()}
    </div>
  );
}

export default DocumentUpload;
