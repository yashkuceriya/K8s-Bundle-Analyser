import { Link } from 'react-router-dom';
import { Shield, Download, RefreshCw, Loader2, ClipboardList, History } from 'lucide-react';

interface NavbarProps {
  bundleName?: string;
  bundleId?: string;
  onReanalyze?: () => void;
  onExport?: () => void;
  onGeneratePlaybook?: () => void;
  onGeneratePreflight?: () => void;
  isReanalyzing?: boolean;
}

export default function Navbar({
  bundleName,
  bundleId,
  onReanalyze,
  onExport,
  onGeneratePlaybook,
  onGeneratePreflight,
  isReanalyzing,
}: NavbarProps) {
  return (
    <nav className="bg-navy-800/80 backdrop-blur-md border-b border-navy-700 sticky top-0 z-50">
      <div className="max-w-screen-2xl mx-auto px-6 h-14 flex items-center justify-between">
        {/* Left: Logo + breadcrumb */}
        <div className="flex items-center gap-4 min-w-0">
          <Link to="/" className="flex items-center gap-2.5 hover:opacity-90 transition-opacity shrink-0">
            <div className="w-8 h-8 bg-gradient-to-br from-[#06b6d4]/20 to-[#8b5cf6]/20 rounded-lg flex items-center justify-center border border-navy-600">
              <Shield size={16} className="text-[#06b6d4]" />
            </div>
            <span className="text-base font-semibold text-white tracking-tight">
              K8s Bundle Analyzer
            </span>
          </Link>
          {bundleName && (
            <div className="flex items-center gap-2 text-sm min-w-0">
              <span className="text-navy-500">/</span>
              <span className="text-gray-300 font-medium truncate max-w-[200px]">{bundleName}</span>
            </div>
          )}
        </div>

        {/* Center: Nav links */}
        <div className="flex items-center gap-1">
          <Link
            to="/"
            className="px-3 py-1.5 text-xs font-medium text-gray-400 hover:text-gray-200 hover:bg-navy-700 rounded-lg transition-all"
          >
            Dashboard
          </Link>
          <Link
            to="/history"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-400 hover:text-gray-200 hover:bg-navy-700 rounded-lg transition-all"
          >
            <History size={14} />
            History
          </Link>
        </div>

        {/* Right: Action buttons */}
        {bundleId && (
          <div className="flex items-center gap-2 shrink-0">
            {onGeneratePreflight && (
              <NavButton onClick={onGeneratePreflight} variant="ghost">
                <Shield size={14} />
                Preflight
              </NavButton>
            )}
            {onGeneratePlaybook && (
              <NavButton onClick={onGeneratePlaybook} variant="ghost">
                <ClipboardList size={14} />
                Playbook
              </NavButton>
            )}
            {onExport && (
              <NavButton onClick={onExport} variant="outline">
                <Download size={14} />
                Export Report
              </NavButton>
            )}
            {onReanalyze && (
              <NavButton onClick={onReanalyze} variant="primary" disabled={isReanalyzing}>
                {isReanalyzing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                Re-analyze
              </NavButton>
            )}
          </div>
        )}
      </div>
    </nav>
  );
}

function NavButton({
  children,
  onClick,
  variant = 'ghost',
  disabled = false,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: 'ghost' | 'outline' | 'primary';
  disabled?: boolean;
}) {
  const base = 'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-all duration-150 disabled:opacity-50';
  const variants = {
    ghost: 'text-gray-400 hover:text-gray-200 hover:bg-navy-700',
    outline: 'border border-navy-600 text-gray-300 hover:bg-navy-700 hover:border-navy-500',
    primary: 'bg-[#06b6d4] hover:bg-cyan-600 text-white shadow-sm shadow-cyan-500/20',
  };
  return (
    <button onClick={onClick} disabled={disabled} className={`${base} ${variants[variant]}`}>
      {children}
    </button>
  );
}
