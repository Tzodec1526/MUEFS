import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';
import MifileComparison from './MifileComparison';
import PlatformStats from './PlatformStats';

function AboutPage() {
  usePageTitle('About');
  return (
    <div className="about-page">
      <PageHeading>About MUEFS</PageHeading>
      <p>
        MUEFS is an open-source demo of one e-filing portal for Michigan courts. It covers filing,
        clerk review, public case search and document delivery. It is not affiliated with SCAO or
        the Michigan Supreme Court, and it is not for real filings.
      </p>
      <MifileComparison />
      <PlatformStats />
    </div>
  );
}

export default AboutPage;
