import { Component } from "react";

/**
 * ErrorBoundary — catches render errors in child components and shows
 * a branded fallback UI instead of a white screen.
 *
 * Usage:
 *   <ErrorBoundary>
 *     <App />
 *   </ErrorBoundary>
 *
 * React error boundaries must be class components.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary" role="alert">
          <div className="error-boundary-card">
            <svg
              width="48"
              height="48"
              viewBox="0 0 28 28"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
              className="error-boundary-logo"
            >
              <rect x="2" y="2" width="14" height="14" rx="3" fill="#0D9488" opacity="0.9" />
              <rect x="12" y="12" width="14" height="14" rx="3" fill="#06B6D4" opacity="0.85" />
              <rect x="9" y="9" width="10" height="10" rx="2" fill="#0C0F1A" opacity="0.6" />
              <rect x="10" y="10" width="8" height="8" rx="1.5" fill="url(#eb-logo-inner)" />
              <defs>
                <linearGradient id="eb-logo-inner" x1="10" y1="10" x2="18" y2="18" gradientUnits="userSpaceOnUse">
                  <stop offset="0%" stopColor="#0D9488" />
                  <stop offset="100%" stopColor="#06B6D4" />
                </linearGradient>
              </defs>
            </svg>

            <h1 className="error-boundary-title">Something went wrong</h1>
            <p className="error-boundary-message">
              An unexpected error occurred. Please reload the page to try again.
            </p>

            <button
              className="btn btn-primary"
              onClick={() => window.location.reload()}
            >
              Reload page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
