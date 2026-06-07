interface LoadErrorProps {
  message?: string;
  onRetry?: () => void;
}

/**
 * A load-failure state that is visually distinct from an empty result, so a network
 * or server error never reads as "there is nothing here." Used on read paths across
 * the app (search, dockets, queues, lists).
 */
function LoadError({ message, onRetry }: LoadErrorProps) {
  return (
    <div className="alert alert-error load-error" role="alert">
      <span>
        {message || "We couldn't load this right now. The system may be temporarily unavailable."}
      </span>
      {onRetry && (
        <button className="btn btn-small btn-secondary" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export default LoadError;
