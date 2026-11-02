import type { PublicPlatformStats } from '../../api/public';

const SEE_STATISTICS = 'See platform statistics';

const rows = (stats: PublicPlatformStats | undefined) => [
  { feature: 'Court coverage', mifile: 'Not all courts or case types', muefs: 'Demo portal (seeded courts)' },
  { feature: 'Public docket search', mifile: 'Varies by court; often separate portals', muefs: 'Built in; no account needed in the demo' },
  { feature: 'Document types', mifile: 'Varies by vendor', muefs: 'A catalog tied to the Michigan Court Rules (MCR)' },
  {
    feature: 'Upload limit',
    mifile: stats ? `${stats.mifile_max_upload_mb} MB` : SEE_STATISTICS,
    muefs: stats ? `${stats.max_upload_mb} MB` : SEE_STATISTICS,
  },
  { feature: 'Fee waiver (MCR 2.002)', mifile: 'Payment screen; court must grant', muefs: 'Part of the filing wizard (demo payments)' },
  { feature: 'Motion companions', mifile: 'Filers must know MCR rules', muefs: 'Checks for them and prompts the filer (MCR 2.119)' },
  { feature: 'File from the case docket', mifile: 'Existing-case filing supported', muefs: 'Filled in from the case page' },
  { feature: 'Clerk review tools', mifile: 'Queue tools vary by court', muefs: 'Batch accept, age badges and quick reject reasons' },
  { feature: 'Case favorites', mifile: 'Not available', muefs: 'Star cases for quick access' },
  {
    feature: 'Service-only records',
    mifile: 'Varies; often a separate workflow',
    muefs: 'Keeps the documents, with opt-in delivery to reviewed recipients; other service methods stay outside the app',
  },
  {
    feature: 'Draft editing',
    mifile: 'Depends on the vendor',
    muefs: 'Save to your account, recover edits in the same tab and compare conflicting versions',
  },
  {
    feature: 'Case participants and access',
    mifile: 'Depends on the court',
    muefs: 'Assigned staff record roles and explicit access grants, and changes are kept',
  },
  {
    feature: 'Reviewed public copies',
    mifile: 'Depends on the court',
    muefs: 'Prepare, check, publish and withdraw a separate PDF; the filed original is kept',
  },
  { feature: 'Cost and license', mifile: 'Per-transaction vendor fees', muefs: 'AGPL-3.0 (no license fee)' },
];

function MifileComparison({ stats }: { stats: PublicPlatformStats | undefined }) {
  return (
    <section className="mifile-comparison" aria-labelledby="mifile-compare-heading">
      <h2 id="mifile-compare-heading">MUEFS compared with MiFILE</h2>
      <table className="mifile-comparison-table">
        <thead>
          <tr>
            <th scope="col">Capability</th>
            <th scope="col">MiFILE</th>
            <th scope="col">MUEFS</th>
          </tr>
        </thead>
        <tbody>
          {rows(stats).map((row) => (
            <tr key={row.feature}>
              <th scope="row">{row.feature}</th>
              <td data-label="MiFILE">{row.mifile}</td>
              <td data-label="MUEFS">{row.muefs}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mifile-comparison-foot">
        Demo comparison, not an SCAO endorsement.{' '}
        <a href="https://github.com/Tzodec1526/MUEFS" target="_blank" rel="noreferrer">
          Source
        </a>
      </p>
    </section>
  );
}

export default MifileComparison;
