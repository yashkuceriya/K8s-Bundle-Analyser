import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import AnalysisView from './pages/AnalysisView';
import HistoryView from './pages/HistoryView';
import CompareView from './pages/CompareView';
import ErrorBoundary from './components/ErrorBoundary';

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary fallback={
        <div className="min-h-screen bg-navy-900 flex items-center justify-center">
          <div className="bg-navy-800 border border-navy-600 rounded-xl p-8 max-w-md text-center space-y-4">
            <div className="w-14 h-14 bg-red-500/10 rounded-xl flex items-center justify-center mx-auto">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-red-400">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>
            <div>
              <p className="text-lg font-semibold text-gray-200">Something went wrong</p>
              <p className="text-sm text-gray-500 mt-1">An unexpected error occurred. Please try again.</p>
            </div>
            <a
              href="/"
              className="inline-block px-5 py-2.5 bg-[#06b6d4] hover:bg-cyan-600 text-white text-sm font-semibold rounded-xl transition-colors"
            >
              Return to Dashboard
            </a>
          </div>
        </div>
      }>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/analysis/:bundleId" element={<AnalysisView />} />
          <Route path="/history" element={<HistoryView />} />
          <Route path="/compare" element={<CompareView />} />
        </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  );
}
