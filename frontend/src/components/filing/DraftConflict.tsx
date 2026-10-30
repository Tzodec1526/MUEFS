import type { RefObject } from 'react';
import { Link } from 'react-router-dom';
import type { FilingEnvelope } from '../../api/filings';

interface DraftConflictProps {
  conflict: FilingEnvelope;
  edits: { caseTitle: string; filingDescription: string };
  headingRef: RefObject<HTMLHeadingElement>;
  onResolve: (keepEdits: boolean) => void;
}

function DraftConflict({ conflict, edits, headingRef, onResolve }: DraftConflictProps) {
  return (
    <section className="review-card draft-conflict" aria-labelledby="draft-conflict-heading">
      <h3 id="draft-conflict-heading" ref={headingRef} tabIndex={-1}>Compare changes before saving</h3>
      <p>Your changes are still here. Compare them with the saved details before continuing.</p>
      <div className="draft-comparison">
        <div><h4>Your edits</h4><strong>{edits.caseTitle || '(No title)'}</strong><p>{edits.filingDescription || '(No description)'}</p></div>
        <div><h4>Saved to your account</h4><strong>{conflict.case_title || '(No title)'}</strong><p>{conflict.filing_description || '(No description)'}</p></div>
      </div>
      <div className="draft-actions">
        <button className="btn btn-secondary" onClick={() => onResolve(false)}>Use saved details</button>
        {['draft', 'returned'].includes(conflict.status)
          ? <button className="btn btn-primary" onClick={() => onResolve(true)}>Keep my edits for next save</button>
          : <Link to={`/filings/${conflict.id}/history`}>This filing is {conflict.status.replace('_', ' ')}. Open its history.</Link>}
      </div>
    </section>
  );
}

export default DraftConflict;
