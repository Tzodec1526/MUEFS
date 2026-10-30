import { Link, useParams } from 'react-router-dom';
import PaymentForm from './PaymentForm';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

export default function FilingFeesPage() {
  const { filingId } = useParams();
  usePageTitle(`Filing #${filingId}: fees and payments`);
  return <section className="filing-fees-page">
    <div className="page-header"><PageHeading>Filing #{filingId}: fees and payments</PageHeading>
      <Link className="btn btn-secondary" to={`/filings/${filingId}/history`}>Receipts &amp; history</Link></div>
    <PaymentForm filingId={Number(filingId)} headingLevel={2} />
  </section>;
}
