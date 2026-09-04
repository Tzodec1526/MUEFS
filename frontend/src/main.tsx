import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import ErrorBoundary from './components/common/ErrorBoundary';
import WebMcpNavigateBridge from './components/agent/WebMcpNavigateBridge';
import { ToastProvider } from './components/common/Toast';
import { initMuefsWebMcp } from './webmcp';
import './styles/global.css';

initMuefsWebMcp();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ToastProvider>
      <BrowserRouter>
        <ErrorBoundary>
          <WebMcpNavigateBridge />
          <App />
        </ErrorBoundary>
      </BrowserRouter>
    </ToastProvider>
  </React.StrictMode>
);
