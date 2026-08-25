import { Check, X, Minus } from 'lucide-react';

type Cell = 'yes' | 'no' | { partial: string } | string;

interface Row {
  feature: string;
  mifile: Cell;
  muefs: Cell;
  highlight?: boolean;
}

const ROWS: Row[] = [
  {
    feature: 'Court coverage',
    mifile: { partial: 'Not all courts or case types' },
    muefs: { partial: 'Demo portal (seeded courts)' },
    highlight: true,
  },
  {
    feature: 'Public docket search',
    mifile: { partial: 'Varies by court; often separate portals' },
    muefs: { partial: 'Built-in; no account in demo' },
    highlight: true,
  },
  { feature: 'Upload limit', mifile: '25 MB', muefs: '100 MB' },
  {
    feature: 'Fee waiver (MCR 2.002)',
    mifile: { partial: 'Payment screen; court must grant' },
    muefs: { partial: 'In filing wizard (demo payments)' },
  },
  {
    feature: 'Motion companions',
    mifile: { partial: 'Filers must know MCR rules' },
    muefs: 'Validates & prompts (MCR 2.119)',
  },
  {
    feature: 'File from case docket',
    mifile: { partial: 'Existing-case filing supported' },
    muefs: 'Pre-filled from case detail',
  },
  {
    feature: 'Clerk review tools',
    mifile: { partial: 'Queue tools vary by court' },
    muefs: 'Batch accept, age badges, quick reject reasons',
  },
  {
    feature: 'AI agent tools (WebMCP)',
    mifile: 'no',
    muefs: { partial: 'Experimental (Chrome flag)' },
    highlight: true,
  },
  {
    feature: 'Case favorites',
    mifile: 'no',
    muefs: 'yes',
  },
  {
    feature: 'Serve documents only',
    mifile: { partial: 'Varies; often separate workflow' },
    muefs: 'One-click from case docket',
  },
  {
    feature: 'Draft autosave',
    mifile: { partial: 'Vendor-dependent' },
    muefs: 'Browser draft recovery',
  },
  {
    feature: 'Cost / licensing',
    mifile: 'Per-transaction vendor fees',
    muefs: 'AGPL-3.0 (no license fee)',
  },
];

function isPartialCell(value: Cell): value is { partial: string } {
  return typeof value === 'object' && value !== null && 'partial' in value;
}

function CellIcon({ value }: { value: 'yes' | 'no' }) {
  if (value === 'yes') return <Check size={18} className="compare-icon compare-yes" aria-hidden />;
  return <X size={18} className="compare-icon compare-no" aria-hidden />;
}

function CellContent({ value }: { value: Cell }) {
  if (value === 'yes' || value === 'no') {
    return (
      <span className="compare-bool">
        <CellIcon value={value} />
        <span className="sr-only">{value}</span>
      </span>
    );
  }
  if (isPartialCell(value)) {
    return (
      <span className="compare-bool compare-partial-cell">
        <Minus size={18} className="compare-icon compare-partial" aria-hidden />
        <span>{value.partial}</span>
      </span>
    );
  }
  return <span>{value}</span>;
}

interface MifileComparisonProps {
  variant?: 'login' | 'dashboard';
}

function MifileComparison({ variant = 'dashboard' }: MifileComparisonProps) {
  return (
    <section
      className={`mifile-comparison mifile-comparison--${variant}`}
      aria-labelledby="mifile-compare-heading"
    >
      <div className="mifile-comparison-header">
        <h2 id="mifile-compare-heading">Why one system beats the patchwork</h2>
        <p>
          Michigan e-filing still spans multiple court systems, vendor contracts, and uneven
          public access. MUEFS is an open-source demo of what a unified portal could look like
          — built for MCR compliance, not vendor rent.
        </p>
      </div>
      <div className="mifile-comparison-table-wrap">
        <table className="mifile-comparison-table">
          <thead>
            <tr>
              <th scope="col">Capability</th>
              <th scope="col">MiFILE / current landscape</th>
              <th scope="col" className="muefs-col">MUEFS (this demo)</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => (
              <tr key={row.feature}>
                <th scope="row">{row.feature}</th>
                <td className={row.highlight ? 'compare-gap' : undefined}>
                  <CellContent value={row.mifile} />
                </td>
                <td className={`muefs-col${row.highlight ? ' compare-gap-muefs' : ''}`}>
                  <CellContent value={row.muefs} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mifile-comparison-foot">
        Comparison reflects this demo build and publicly documented MiFILE limits (e.g. 25 MB per
        SCAO filing standards). Not an official court endorsement.
        {' '}
        <a href="https://github.com/Tzodec1526/MUEFS" target="_blank" rel="noreferrer">
          View source on GitHub
        </a>
      </p>
    </section>
  );
}

export default MifileComparison;
