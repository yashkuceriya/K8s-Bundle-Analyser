import { Link, useLocation } from 'react-router-dom';
import { Search, Bell, Settings } from 'lucide-react';
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

export default function Navbar(_props: NavbarProps) {
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
    <nav className="bg-navy-900 border-b border-navy-700 sticky top-0 z-50">
      <div className="px-6 h-14 flex items-center justify-between">
        {/* Left: Logo */}
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

        {/* Center: Nav links */}
        <div className="flex items-center gap-1">
          {navLinks.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className={clsx(
                'px-4 py-1.5 text-sm font-medium rounded-lg transition-all duration-150',
                isActive(link.to)
                  ? 'text-white'
                  : 'text-gray-400 hover:text-gray-200'
              )}
            >
              {link.label}
            </Link>
          ))}
        </div>

        {/* Right: Search + Icons */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              type="text"
              placeholder="Search resources..."
              className="w-48 bg-navy-800 border border-navy-700 rounded-lg pl-9 pr-3 py-1.5 text-sm text-gray-300 outline-none focus:border-accent-blue/50 placeholder-gray-600"
            />
          </div>
          <button className="p-2 text-gray-400 hover:text-gray-200 hover:bg-navy-800 rounded-lg transition-colors">
            <Bell size={18} />
          </button>
          <button className="p-2 text-gray-400 hover:text-gray-200 hover:bg-navy-800 rounded-lg transition-colors">
            <Settings size={18} />
          </button>
          <div className="w-8 h-8 bg-gradient-to-br from-accent-blue to-accent-purple rounded-full flex items-center justify-center text-white text-xs font-bold">
            U
          </div>
        </div>
      </div>
    </nav>
  );
}
