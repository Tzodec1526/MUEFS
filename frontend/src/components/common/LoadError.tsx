import type { LoadFailure } from '../../utils/errors';

interface LoadErrorProps {
  failure: LoadFailure;
  onRetry?: () => void;
}

function LoadError({ failure, onRetry }: LoadErrorProps) {
  return (
    <div className="alert alert-error load-error" role="alert">
      <span>{failure.message}</span>
      {onRetry && failure.retry && (
        <button className="btn btn-small btn-secondary" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export default LoadError;
