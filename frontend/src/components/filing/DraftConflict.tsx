import type { RefObject } from 'react';
import { Link } from 'react-router-dom';
import type { FilingEnvelope } from '../../api/filings';
import { filingStatusLabel } from '../../utils/filingStatus';

interface DraftConflictProps {
  conflict: FilingEnvelope;
  edits: { caseTitle: string; filingDescription: string };
  headingRef: RefObject<HTMLHeadingElement>;
  onResolve: (keepEdits: boolean) => void;
}

function DraftConflict({ conflict, edits, headingRef, onResolve }: DraftConflictProps) {
  return (
    <section className="review-card draft-conflict" aria-labelledby="draft-conflict-heading">
      <h2 id="draft-conflict-heading" ref={headingRef} tabIndex={-1}>Compare changes before saving</h2>
      <p>Your changes are still here. Compare them with the saved details before continuing.</p>
      <div className="draft-comparison">
        <div><h3>Your edits</h3><strong>{edits.caseTitle || '(No title)'}</strong><p>{edits.filingDescription || '(No description)'}</p></div>
        <div><h3>Saved to your account</h3><strong>{conflict.case_title || '(No title)'}</strong><p>{conflict.filing_description || '(No description)'}</p></div>
      </div>
      <div className="draft-actions">
        <button className="btn btn-secondary" onClick={() => onResolve(false)}>Use saved details</button>
        {['draft', 'returned'].includes(conflict.status)
          ? <button className="btn btn-primary" onClick={() => onResolve(true)}>Keep my edits for next save</button>
          : <Link to={`/filings/${conflict.id}/history`}>Status: {filingStatusLabel(conflict.status)}. Open its history.</Link>}
      </div>
    </section>
  );
}

export default DraftConflict;
