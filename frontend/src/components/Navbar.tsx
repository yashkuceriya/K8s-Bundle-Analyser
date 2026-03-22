import { Link, useLocation } from 'react-router-dom';
import { RefreshCw, Download, Loader2, Search, Bell, Settings } from 'lucide-react';
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
    { to: '/compare', label: 'Compare' },
  ];

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  return (
    <nav className="fixed top-0 w-full z-50 bg-[#0b1326]/80 backdrop-blur-md border-b border-outline-variant/15 shadow-[0_12px_32px_rgba(194,198,214,0.06)]">
      <div className="px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-8">
          <Link to="/" className="hover:opacity-90 transition-opacity shrink-0">
            <span className="text-xl font-black text-primary tracking-tighter font-headline">K8s Bundle Analyzer</span>
          </Link>
          <div className="hidden md:flex items-center gap-6">
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={clsx(
                  'font-headline font-bold tracking-tight transition-colors',
                  isActive(link.to)
                    ? 'text-primary border-b-2 border-primary pb-1'
                    : 'text-on-surface-variant hover:text-primary'
                )}
              >
                {link.label}
              </Link>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-4">
          {bundleName && (
            <div className="hidden lg:flex items-center gap-3 mr-2">
              <span className="text-xs text-on-surface-variant font-mono truncate max-w-[200px]">{bundleName}</span>
              {onExport && (
                <button onClick={onExport} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-on-surface-variant bg-surface-container hover:bg-surface-container-high rounded-lg transition-colors border border-outline-variant/20">
                  <Download size={12} /> Export
                </button>
              )}
              {onReanalyze && (
                <button onClick={onReanalyze} disabled={isReanalyzing} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold text-white bg-primary-container hover:brightness-110 rounded-lg transition-all disabled:opacity-50 shadow-lg shadow-primary-container/20">
                  {isReanalyzing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                  Re-analyze
                </button>
              )}
            </div>
          )}
          <div className="relative hidden sm:block">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant" />
            <input type="text" placeholder="Search resources..." className="bg-surface-container border-none rounded-lg py-1.5 pl-10 pr-4 text-sm focus:ring-1 focus:ring-primary w-64 text-on-surface-variant placeholder:text-on-surface-variant/50" />
          </div>
          <button className="p-2 text-on-surface-variant hover:bg-surface-container-high transition-all duration-200 rounded-lg active:scale-95"><Bell size={18} /></button>
          <button className="p-2 text-on-surface-variant hover:bg-surface-container-high transition-all duration-200 rounded-lg active:scale-95"><Settings size={18} /></button>
          <div className="h-8 w-8 rounded-full bg-primary-container flex items-center justify-center text-xs font-bold text-white border border-outline-variant/30">U</div>
        </div>
      </div>
    </nav>
  );
}
