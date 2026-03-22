import { Link, useLocation } from 'react-router-dom';
import { RefreshCw, Download, Loader2 } from 'lucide-react';
import clsx from 'clsx';

interface NavbarProps {
  bundleName?: string;
  bundleId?: string;
  onReanalyze?: () => void;
  onExport?: () => void;
  onGeneratePlaybook?: () => void;
  onGeneratePreflight?: () => void;
  isReanalyzing?: boolean;
}

export default function Navbar({ bundleName, onReanalyze, onExport, isReanalyzing }: NavbarProps) {
  const location = useLocation();

  const navLinks = [
    { to: '/', label: 'Dashboard' },
    { to: '/history', label: 'History' },
  ];

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  return (
    <nav className="bg-navy-900 border-b border-navy-700 sticky top-0 z-50">
      <div className="px-6 h-14 flex items-center justify-between">
        {/* Left: Logo + Nav */}
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-center gap-2 hover:opacity-90 transition-opacity shrink-0">
            <div className="w-7 h-7 bg-accent-blue/20 rounded-lg flex items-center justify-center">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-accent-blue">
                <path d="M12 2L2 7l10 5 10-5-10-5z" />
                <path d="M2 17l10 5 10-5" />
                <path d="M2 12l10 5 10-5" />
              </svg>
            </div>
            <span className="text-base font-bold text-white tracking-tight">K8s Bundle Analyzer</span>
          </Link>

          <div className="flex items-center gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={clsx(
                  'px-3 py-1.5 text-sm font-medium rounded-lg transition-all duration-150',
                  isActive(link.to)
                    ? 'text-white bg-navy-800'
                    : 'text-gray-400 hover:text-gray-200'
                )}
              >
                {link.label}
              </Link>
            ))}
          </div>
        </div>

        {/* Right: Bundle context (only on analysis page) */}
        {bundleName && (
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500 font-mono truncate max-w-[200px]">{bundleName}</span>
            {onExport && (
              <button
                onClick={onExport}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-300 bg-navy-800 hover:bg-navy-700 rounded-lg transition-colors border border-navy-700"
              >
                <Download size={12} />
                Export
              </button>
            )}
            {onReanalyze && (
              <button
                onClick={onReanalyze}
                disabled={isReanalyzing}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-accent-blue hover:bg-blue-600 rounded-lg transition-colors disabled:opacity-50"
              >
                {isReanalyzing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                Re-analyze
              </button>
            )}
          </div>
        )}
      </div>
    </nav>
  );
}
