import { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  errorMessage: string;
}

class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, errorMessage: '' };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, errorMessage: error.message };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Console is visible in dev tools and surfaces in browser-side error reporters.
    // eslint-disable-next-line no-console
    console.error('Render error:', error, info.componentStack);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, errorMessage: '' });
  };

  render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }
    return (
      <div className="error-boundary" role="alert">
        <h2>Something went wrong.</h2>
        <p>
          The portal hit an unexpected error rendering this view. Your work-in-progress
          draft (if any) is safe in this browser.
        </p>
        {this.state.errorMessage && (
          <p className="error-detail"><code>{this.state.errorMessage}</code></p>
        )}
        <div className="error-actions">
          <button className="btn btn-primary" onClick={() => window.location.assign('/')}>
            Return to Dashboard
          </button>
          <button className="btn btn-secondary" onClick={this.handleReset}>
            Try Again
          </button>
        </div>
      </div>
    );
  }
}

export default ErrorBoundary;
