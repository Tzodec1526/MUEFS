import type { FilingDraft } from '../../utils/filingDraft';
import type { LoadFailure } from '../../utils/errors';
import LoadError from '../common/LoadError';

interface DetailsStepProps {
  filingData: Pick<FilingDraft, 'filingType' | 'caseTitle' | 'filingDescription'>;
  existingCase: boolean;
  captionMissing: boolean;
  caseLookupError: LoadFailure | null;
  retryCaseLookup: () => void;
  destinationLocked: boolean;
  saving: boolean;
  updateData: (updates: Partial<FilingDraft>) => void;
}

function DetailsStep({
  filingData, existingCase, captionMissing, caseLookupError, retryCaseLookup, destinationLocked, saving, updateData,
}: DetailsStepProps) {
  return (
    <div className="form-section">
      <h2>{existingCase ? 'Filing Details' : 'Case Details'}</h2>

      {captionMissing && caseLookupError && (
        <LoadError failure={{ ...caseLookupError, message: `${caseLookupError.message} Retry, or go Back to choose the case.` }}
          onRetry={retryCaseLookup} />
      )}

      {existingCase && (
        <fieldset className="form-group filing-type-fieldset">
          <legend>Filing Type <span className="required-marker">*</span></legend>
          <div className="filing-type-options">
            <label className={`filing-type-option ${filingData.filingType === 'subsequent' ? 'selected' : ''}`}>
              <input
                type="radio"
                name="filingType"
                value="subsequent"
                checked={filingData.filingType === 'subsequent'}
                disabled={destinationLocked || saving}
                onChange={() => updateData({ filingType: 'subsequent' })}
              />
              <div>
                <strong>File with Court</strong>
                <span>Document is filed with the court and reviewed by the clerk. Appears on the docket.</span>
              </div>
            </label>
            <label className={`filing-type-option ${filingData.filingType === 'service_only' ? 'selected' : ''}`}>
              <input
                type="radio"
                name="filingType"
                value="service_only"
                checked={filingData.filingType === 'service_only'}
                disabled={destinationLocked || saving}
                onChange={() => updateData({ filingType: 'service_only' })}
              />
              <div>
                <strong>Service Only (No Court Filing)</strong>
                <span>Record documents for service outside this app. No court filing, clerk review, or filing fee. This app does not deliver documents to other parties.</span>
              </div>
            </label>
          </div>
        </fieldset>
      )}

      <p className="info-text">
        {filingData.filingType === 'service_only'
          ? 'Describe the documents you are recording. You must arrange delivery to the other parties outside this app.'
          : existingCase
          ? 'Describe your filing. The case title is pre-filled from the existing case.'
          : <>Enter the case information. Fields marked with <span className="required-marker">*</span> are required.</>
        }
      </p>
      <div className="form-group">
        <label htmlFor="caseTitle">
          Case Title <span className="required-marker">*</span>
        </label>
        <input
          id="caseTitle"
          disabled={saving}
          type="text"
          value={filingData.caseTitle}
          onChange={(e) => updateData({ caseTitle: e.target.value })}
          placeholder="e.g., Smith v. Jones"
          aria-required="true"
          readOnly={existingCase}
          autoFocus={!existingCase}
        />
        {!existingCase && (
          <span className="field-hint">
            Format: Plaintiff name v. Defendant name (e.g., &quot;Smith v. Jones&quot;)
          </span>
        )}
      </div>
      <div className="form-group">
        <label htmlFor="filingDesc">
          {filingData.filingType === 'service_only' ? 'Service Description' : 'Filing Description'} <span className="required-marker">*</span>
        </label>
        <textarea
          id="filingDesc"
          disabled={saving}
          value={filingData.filingDescription}
          onChange={(e) => updateData({ filingDescription: e.target.value })}
          placeholder={filingData.filingType === 'service_only'
            ? "e.g., Plaintiff's First Set of Interrogatories (MCR 2.309)"
            : existingCase
            ? 'e.g., Answer to the complaint'
            : "Brief description of this filing (e.g., Initial complaint for breach of contract)..."
          }
          autoFocus={existingCase}
          rows={4}
        />
      </div>
    </div>
  );
}

export default DetailsStep;
