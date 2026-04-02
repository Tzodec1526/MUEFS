import { useState, useRef } from 'react';
import { uploadDocument, removeDocument } from '../../api/filings';

interface DocumentInfo {
  id: number;
  title: string;
  type: string;
  size: number;
}

interface Props {
  filingId: number;
  courtId: number;
  caseTypeId: number;
  documents: DocumentInfo[];
  onDocumentsChange: (docs: DocumentInfo[]) => void;
}

const DOCUMENT_TYPES = [
  { code: 'COMPLAINT', label: 'Complaint' },
  { code: 'ANSWER', label: 'Answer' },
  { code: 'MOTION', label: 'Motion' },
  { code: 'BRIEF', label: 'Brief/Memorandum' },
  { code: 'AFFIDAVIT', label: 'Affidavit' },
  { code: 'EXHIBIT', label: 'Exhibit' },
  { code: 'ORDER', label: 'Proposed Order' },
  { code: 'SUMMONS', label: 'Summons' },
  { code: 'PROOF_SERVICE', label: 'Proof of Service' },
  { code: 'STIPULATION', label: 'Stipulation' },
  { code: 'NOTICE', label: 'Notice' },
  { code: 'OTHER', label: 'Other' },
];

// courtId and caseTypeId reserved for future filing requirements display
function DocumentUpload({
  filingId,
  courtId: _courtId,
  caseTypeId: _caseTypeId,
  documents,
  onDocumentsChange,
}: Props) {
  const [uploading, setUploading] = useState(false);
  const [docType, setDocType] = useState('COMPLAINT');
  const [docTitle, setDocTitle] = useState('');
  const [isConfidential, setIsConfidential] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleUpload = async () => {
    const file = fileInputRef.current?.files?.[0];
    if (!file) {
      setError('Please select a file');
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
        { id: result.id, title: result.title, type: docType, size: result.file_size_bytes },
      ]);
      setDocTitle('');
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

  return (
    <div className="form-section">
      <h3>Upload Documents</h3>
      <p className="info-text">
        Upload your filing documents. All documents must be in PDF format (preferred),
        Word, TXT, RTF, or image format. Maximum file size: 100MB per document.
        PDFs must be text-searchable per MCR 1.109.
      </p>

      {error && <div className="alert alert-error">{error}</div>}

      {/* Upload Form */}
      <div className="upload-form">
        <div className="form-group">
          <label htmlFor="docType">Document Type</label>
          <select id="docType" value={docType} onChange={(e) => setDocType(e.target.value)}>
            {DOCUMENT_TYPES.map((dt) => (
              <option key={dt.code} value={dt.code}>
                {dt.label}
              </option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label htmlFor="docTitle">Document Title</label>
          <input
            id="docTitle"
            type="text"
            value={docTitle}
            onChange={(e) => setDocTitle(e.target.value)}
            placeholder="e.g., Complaint for Breach of Contract"
          />
        </div>
        <div className="form-group">
          <label htmlFor="docFile">File</label>
          <input
            id="docFile"
            type="file"
            ref={fileInputRef}
            accept=".pdf,.doc,.docx,.txt,.rtf,.tiff,.tif,.jpg,.jpeg,.png"
          />
        </div>
        <div className="form-group checkbox">
          <label>
            <input
              type="checkbox"
              checked={isConfidential}
              onChange={(e) => setIsConfidential(e.target.checked)}
            />
            Mark as confidential
          </label>
        </div>
        <button
          className="btn btn-primary"
          onClick={handleUpload}
          disabled={uploading}
        >
          {uploading ? 'Uploading...' : 'Upload Document'}
        </button>
      </div>

      {/* Uploaded Documents List */}
      {documents.length > 0 && (
        <div className="uploaded-documents">
          <h4>Uploaded Documents ({documents.length})</h4>
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Size</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id}>
                  <td>{doc.title}</td>
                  <td>{doc.type}</td>
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
    </div>
  );
}

export default DocumentUpload;
