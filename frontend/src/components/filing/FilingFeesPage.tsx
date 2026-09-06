import { Link, useParams } from 'react-router-dom';
import PaymentForm from './PaymentForm';

export default function FilingFeesPage() {
  const { filingId } = useParams();
  return <section className="filing-fees-page">
    <div className="page-header"><h2>Filing #{filingId}: fees &amp; payments</h2>
      <Link className="btn btn-secondary" to={`/filings/${filingId}/history`}>Receipts &amp; history</Link></div>
    <PaymentForm filingId={Number(filingId)} />
  </section>;
}
