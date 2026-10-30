import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import ErrorBoundary from './components/common/ErrorBoundary';
import { ToastProvider } from './components/common/Toast';
import { handleKeycloakCallback, migrateStoredToken } from './auth/keycloak';
import './styles/global.css';

migrateStoredToken();

const root = ReactDOM.createRoot(document.getElementById('root')!);
function renderApp() {
  root.render(
    <React.StrictMode>
      <ToastProvider>
        <BrowserRouter>
          <ErrorBoundary>
            <App />
          </ErrorBoundary>
        </BrowserRouter>
      </ToastProvider>
    </React.StrictMode>,
  );
}

if (window.location.pathname === '/auth/callback') {
  root.render(<p className="loading" role="status">Completing sign-in…</p>);
  void handleKeycloakCallback().catch(() => {}).finally(renderApp);
} else renderApp();
