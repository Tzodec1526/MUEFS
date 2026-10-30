import type { LoadFailure } from '../../utils/errors';
import LoadError from './LoadError';
import PageHeading from './PageHeading';

export default function PageLoadError({ heading, failure, onRetry }: {
  heading: string; failure: LoadFailure; onRetry?: () => void;
}) {
  return (
    <div>
      <PageHeading>{heading}</PageHeading>
      <LoadError failure={failure} onRetry={onRetry} />
    </div>
  );
}
