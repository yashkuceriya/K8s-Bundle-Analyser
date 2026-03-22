import { useState, useEffect, useMemo, useCallback, lazy, Suspense } from 'react';
import { useParams, Link } from 'react-router-dom';
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer } from 'recharts';
import {
  LayoutDashboard,
  AlertTriangle,
  FileText,
  Network,
  Box,
  Search,
  Filter,
  MessageCircle,
  Zap,
  Loader2,
  RefreshCw,
  Sparkles,
  AlertCircle,
} from 'lucide-react';
import { format } from 'date-fns';
import clsx from 'clsx';
import Navbar from '../components/Navbar';
import LoadingSpinner from '../components/LoadingSpinner';
import IssueCard from '../components/IssueCard';
import HealthScore from '../components/HealthScore';
const ClusterMap = lazy(() => import('../components/ClusterMap'));
import ClusterHealthGrid from '../components/ClusterHealthGrid';
import LogCorrelationView from '../components/LogCorrelationView';
import BundleChat from '../components/BundleChat';
import ErrorBoundary from '../components/ErrorBoundary';
import { PlaybookModal } from '../components/PlaybookExport';
import PreflightViewer from '../components/PreflightViewer';
import { getAnalysis, getBundle, reanalyzeBundle, exportReport, getAnalysisHistory } from '../api/client';
import type { AnalysisResult, BundleInfo, Issue, LogEntry, AnalysisHistoryEntry } from '../types';

type Tab = 'overview' | 'issues' | 'cluster-map' | 'logs' | 'chat' | 'log-correlation';

const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'overview', label: 'Overview', icon: <LayoutDashboard size={18} /> },
  { id: 'issues', label: 'Issues', icon: <AlertTriangle size={18} /> },
  { id: 'cluster-map', label: 'Cluster Map', icon: <Network size={18} /> },
  { id: 'log-correlation', label: 'Correlations', icon: <Zap size={18} /> },
  { id: 'logs', label: 'Logs', icon: <FileText size={18} /> },
  { id: 'chat', label: 'Chat', icon: <MessageCircle size={18} /> },
];

export default function AnalysisView() {
  const { bundleId } = useParams<{ bundleId: string }>();
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [bundle, setBundle] = useState<BundleInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [isReanalyzing, setIsReanalyzing] = useState(false);
  const [playbookOpen, setPlaybookOpen] = useState(false);
  const [preflightOpen, setPreflightOpen] = useState(false);
  const [historyData, setHistoryData] = useState<AnalysisHistoryEntry[]>([]);

  const fetchData = useCallback(async () => {
    if (!bundleId) return;
    try {
      const [a, b] = await Promise.all([getAnalysis(bundleId), getBundle(bundleId)]);
      setAnalysis(a);
      setBundle(b);
      try {
        const hist = await getAnalysisHistory(bundleId);
        setHistoryData(hist);
      } catch { /* history may not exist */ }
    } catch {
      setError('Failed to load analysis. The bundle may not have been analyzed yet.');
    } finally {
      setLoading(false);
    }
  }, [bundleId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const tabIndex = parseInt(e.key) - 1;
      if (tabIndex >= 0 && tabIndex < tabs.length) {
        setActiveTab(tabs[tabIndex].id);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const handleReanalyze = async () => {
    if (!bundleId) return;
    setIsReanalyzing(true);
    try {
      const result = await reanalyzeBundle(bundleId);
      setAnalysis(result);
    } catch {
      // Refetch on failure as well
      await fetchData();
    } finally {
      setIsReanalyzing(false);
    }
  };

  const handleExport = async () => {
    if (!bundleId) return;
    try {
      const blob = await exportReport(bundleId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report-${bundleId}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      // silently handle export error
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-surface pt-16">
        <Navbar />
        <div className="flex items-center justify-center h-[80vh]">
          <LoadingSpinner size={40} label="Loading analysis..." />
        </div>
      </div>
    );
  }

  if (error || !analysis) {
    return (
      <div className="min-h-screen bg-surface pt-16">
        <Navbar />
        <div className="flex flex-col items-center justify-center h-[80vh] gap-4">
          <AlertTriangle size={48} className="text-error" />
          <p className="text-on-surface-variant">{error || 'Analysis not found'}</p>
          <Link
            to="/"
            className="mt-2 text-sm text-primary hover:text-primary-container transition-colors hover:underline"
          >
            Go back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface flex flex-col">
      <Navbar
        bundleName={bundle?.filename}
        bundleId={bundleId}
        onReanalyze={handleReanalyze}
        onExport={handleExport}
        onGeneratePlaybook={() => setPlaybookOpen(true)}
        onGeneratePreflight={() => setPreflightOpen(true)}
        isReanalyzing={isReanalyzing}
      />

      <div className="flex flex-1 pt-16">
        {/* Left Sidebar */}
        <aside className="w-64 shrink-0 bg-surface-container-low fixed left-0 top-16 h-[calc(100vh-64px)] flex flex-col p-4 space-y-2 z-40">
          {/* Bundle Info */}
          <div className="px-2 py-4 mb-4 bg-surface-container-high/40 rounded-xl">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-primary/10 rounded-lg">
                <Network size={18} className="text-primary" />
              </div>
              <div className="min-w-0">
                <p className="text-primary font-bold text-sm tracking-tight truncate">{bundle?.filename?.replace('.tar.gz', '') || 'Bundle'}</p>
                <p className="text-[0.625rem] text-primary/70 uppercase tracking-widest font-bold">Health Score: {analysis.cluster_health.score}</p>
              </div>
            </div>
          </div>

          {/* Navigation */}
          <div className="flex-1 space-y-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={clsx(
                  'sidebar-item w-full',
                  activeTab === tab.id ? 'sidebar-item-active' : 'sidebar-item-inactive'
                )}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>

          {/* Bottom Actions */}
          <div className="mt-auto pt-4 border-t border-outline-variant/10 space-y-2">
            <button
              onClick={handleReanalyze}
              disabled={isReanalyzing}
              className="w-full py-3 bg-primary-container text-white font-bold rounded-lg text-[0.6875rem] uppercase tracking-wider hover:brightness-110 transition-all active:scale-[0.98] shadow-lg shadow-primary-container/20 flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {isReanalyzing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              Re-analyze Bundle
            </button>

            <button
              onClick={() => setPreflightOpen(true)}
              className="w-full py-2.5 bg-surface-container hover:bg-surface-container-high text-on-surface-variant font-bold rounded-lg text-[0.6875rem] uppercase tracking-wider transition-all flex items-center justify-center gap-2 border border-outline-variant/20"
            >
              <Box size={14} />
              Preflight Export
            </button>

            <button
              onClick={() => setPlaybookOpen(true)}
              className="w-full py-2.5 bg-surface-container hover:bg-surface-container-high text-on-surface-variant font-bold rounded-lg text-[0.6875rem] uppercase tracking-wider transition-all flex items-center justify-center gap-2 border border-outline-variant/20"
            >
              <FileText size={14} />
              Export Playbook
            </button>

            <p className="text-[9px] text-outline text-center mt-2">Press 1-6 to switch tabs</p>
          </div>
        </aside>

        {/* Main Content */}
        <div className="flex-1 flex flex-col min-w-0 ml-64">
          {/* Tab Content */}
          <main className="flex-1 p-8 overflow-auto bg-surface-container-lowest/30">
            {activeTab === 'overview' && (
              <OverviewTab analysis={analysis} historyData={historyData} onOpenPlaybook={() => setPlaybookOpen(true)} />
            )}
            {activeTab === 'issues' && <IssuesTab issues={analysis.issues} />}
            {activeTab === 'log-correlation' && (
              <ErrorBoundary fallback={<div className="bg-navy-800 border border-navy-600 rounded-xl p-8 text-center"><p className="text-sm text-gray-400">Log correlation failed to load</p></div>}>
                <LogCorrelationView correlations={analysis.correlations ?? []} />
              </ErrorBoundary>
            )}
            {activeTab === 'logs' && <LogViewerTab logs={analysis.log_entries} />}
            {activeTab === 'cluster-map' && (
              <div className="space-y-6">
                <ClusterHealthGrid resourceHealth={analysis.resource_health ?? []} />
                <ErrorBoundary fallback={<div className="flex items-center justify-center h-[600px] bg-navy-800 rounded-xl border border-navy-600"><p className="text-sm text-gray-400">3D visualization unavailable</p></div>}>
                  <Suspense fallback={<div className="flex items-center justify-center h-[600px] bg-navy-800 rounded-xl border border-navy-600"><div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" /></div>}>
                    <ClusterMap nodes={analysis.topology_nodes} edges={analysis.topology_edges} />
                  </Suspense>
                </ErrorBoundary>
              </div>
            )}
            {activeTab === 'chat' && bundleId && (
              <ErrorBoundary fallback={<div className="p-8 text-center"><p className="text-sm text-gray-400">Chat unavailable</p></div>}>
                <div className="max-w-4xl mx-auto h-[calc(100vh-12rem)]">
                  <BundleChat bundleId={bundleId} />
                </div>
              </ErrorBoundary>
            )}
          </main>
        </div>
      </div>

      {/* Playbook Modal */}
      {playbookOpen && (
        <PlaybookModal analysis={analysis} bundleFilename={bundle?.filename} onClose={() => setPlaybookOpen(false)} />
      )}

      {/* Preflight Viewer Modal */}
      {preflightOpen && bundleId && (
        <PreflightViewer bundleId={bundleId} onClose={() => setPreflightOpen(false)} />
      )}
    </div>
  );
}

/* ============================================================ */
/* Overview Tab                                                  */
/* ============================================================ */

function OverviewTab({
  analysis,
  historyData,
  onOpenPlaybook,
}: {
  analysis: AnalysisResult;
  historyData: AnalysisHistoryEntry[];
  onOpenPlaybook: () => void;
}) {
  const { cluster_health: health, issues, summary } = analysis;

  // Issue categories for the bar chart
  const categoryData = useMemo(() => {
    const counts: Record<string, number> = {};
    issues.forEach(i => { counts[i.category] = (counts[i.category] || 0) + 1; });
    return Object.entries(counts)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 6);
  }, [issues]);

  return (
    <div className="space-y-6 max-w-screen-2xl">
      {/* Stats Row — single glanceable strip */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {/* Health Score */}
        <div className="col-span-1 bg-navy-800 border border-navy-700 rounded-xl p-5 flex flex-col items-center justify-center">
          <HealthScore score={health.score} size={120} trend={historyData.length > 1 ? historyData.map(h => h.health_score) : undefined} />
        </div>

        {/* Critical Issues */}
        <div className="bg-navy-800 border border-navy-700 rounded-xl p-5 flex flex-col justify-between">
          <div className="flex items-center gap-2 mb-2">
            <AlertCircle size={16} className="text-red-400" />
            <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">Critical Issues</span>
          </div>
          <span className="text-4xl font-bold text-red-400" style={{ textShadow: '0 0 20px rgba(239,68,68,0.3)' }}>{health.critical_count}</span>
          <span className="text-[10px] text-gray-600 mt-1">detected problems</span>
        </div>

        {/* Warning Issues */}
        <div className="bg-navy-800 border border-navy-700 rounded-xl p-5 flex flex-col justify-between">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={16} className="text-amber-400" />
            <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">Warning Issues</span>
          </div>
          <span className="text-4xl font-bold text-amber-400" style={{ textShadow: '0 0 20px rgba(245,158,11,0.3)' }}>{health.warning_count}</span>
          <span className="text-[10px] text-gray-600 mt-1">potential concerns</span>
        </div>

        {/* Nodes & Pods */}
        <div className="bg-navy-800 border border-navy-700 rounded-xl p-5 flex flex-col justify-between">
          <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2">Infrastructure</span>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400">Nodes</span>
              <span className="text-sm font-bold text-white">{health.node_count}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400">Pods</span>
              <span className="text-sm font-bold text-white">{health.pod_count}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400">Namespaces</span>
              <span className="text-sm font-bold text-white">{health.namespace_count}</span>
            </div>
          </div>
        </div>

        {/* Issue Categories */}
        <div className="bg-navy-800 border border-navy-700 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">By Category</span>
            <span className="text-[10px] text-gray-600">{issues.length} total</span>
          </div>
          <div className="h-28">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={categoryData} layout="vertical" margin={{ left: 0, right: 4, top: 0, bottom: 0 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 9, fill: '#6b7280' }} width={72} axisLine={false} tickLine={false} />
                <Bar dataKey="value" fill="#06b6d4" radius={[0, 4, 4, 0]} barSize={10} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* AI Summary + Insights */}
      {(summary || (analysis.ai_insights && analysis.ai_insights.length > 0)) && (
        <div className="bg-navy-800 border border-navy-700 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles size={16} className="text-accent-blue" />
            <h3 className="text-sm font-semibold text-white uppercase tracking-wider">AI Analysis</h3>
          </div>
          {summary && (
            <p className="text-sm text-gray-400 leading-relaxed mb-4">{summary}</p>
          )}
          {analysis.ai_insights && analysis.ai_insights.length > 0 && (
            <ul className="space-y-2 border-t border-navy-700 pt-3">
              {analysis.ai_insights.map((insight, i) => (
                <li key={i} className="flex items-start gap-2.5 text-sm text-gray-400 leading-relaxed">
                  <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-accent-blue shrink-0" />
                  {insight}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Cluster Health Grid */}
      {analysis.resource_health && analysis.resource_health.length > 0 && (
        <ClusterHealthGrid resourceHealth={analysis.resource_health} />
      )}

      {/* Top Findings */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-white uppercase tracking-wider">Top Issues</h3>
          <button
            onClick={onOpenPlaybook}
            className="flex items-center gap-2 px-4 py-2 bg-accent-blue hover:bg-blue-600 text-white text-xs font-semibold rounded-lg transition-all"
          >
            <Zap size={14} />
            Export Playbook
          </button>
        </div>
        <div className="space-y-3">
          {issues
            .sort((a, b) => {
              const order: Record<string, number> = { critical: 0, warning: 1, info: 2 };
              return (order[a.severity] ?? 3) - (order[b.severity] ?? 3);
            })
            .slice(0, 8)
            .map((issue) => (
              <IssueCard key={issue.id} issue={issue} />
            ))}
        </div>
      </div>
    </div>
  );
}

/* ============================================================ */
/* Issues Tab                                                    */
/* ============================================================ */

function IssuesTab({ issues }: { issues: Issue[] }) {
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');

  const categories = useMemo(
    () => ['all', ...Array.from(new Set(issues.map((i) => i.category)))],
    [issues]
  );

  const filtered = useMemo(() => {
    return issues.filter((issue) => {
      if (severityFilter !== 'all' && issue.severity !== severityFilter) return false;
      if (categoryFilter !== 'all' && issue.category !== categoryFilter) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        return (
          issue.title.toLowerCase().includes(q) ||
          issue.description.toLowerCase().includes(q) ||
          (issue.resource ?? '').toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [issues, severityFilter, categoryFilter, searchQuery]);

  return (
    <div className="max-w-screen-xl space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 bg-navy-800 border border-navy-600 rounded-xl p-4">
        <Filter size={16} className="text-gray-500" />
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          aria-label="Filter by severity"
          className="bg-navy-700 border border-navy-600 rounded-lg px-3 py-1.5 text-sm text-gray-300 outline-none focus:border-[#06b6d4]"
        >
          <option value="all">All Severities</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          aria-label="Filter by category"
          className="bg-navy-700 border border-navy-600 rounded-lg px-3 py-1.5 text-sm text-gray-300 outline-none focus:border-[#06b6d4]"
        >
          {categories.map((c) => (
            <option key={c} value={c}>
              {c === 'all' ? 'All Categories' : c}
            </option>
          ))}
        </select>
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Search issues..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search issues"
            className="w-full bg-navy-700 border border-navy-600 rounded-lg pl-9 pr-3 py-1.5 text-sm text-gray-300 outline-none focus:border-[#06b6d4] placeholder-gray-600"
          />
        </div>
        <span className="text-xs text-gray-500">{filtered.length} issues</span>
      </div>

      {/* Issue List */}
      {filtered.length === 0 ? (
        <div className="bg-navy-700 border border-navy-600 rounded-xl p-12 text-center text-gray-500">
          No issues match the current filters
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((issue) => (
            <IssueCard key={issue.id} issue={issue} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ============================================================ */
/* Log Viewer Tab                                                */
/* ============================================================ */

function LogViewerTab({ logs }: { logs: LogEntry[] }) {
  const [levelFilter, setLevelFilter] = useState<string>('all');
  const [nsFilter, setNsFilter] = useState<string>('all');
  const [podFilter, setPodFilter] = useState<string>('all');
  const [searchText, setSearchText] = useState('');

  const namespaces = useMemo(
    () => ['all', ...Array.from(new Set(logs.map((l) => l.namespace).filter(Boolean)))],
    [logs]
  );
  const pods = useMemo(
    () => ['all', ...Array.from(new Set(logs.map((l) => l.pod).filter(Boolean)))],
    [logs]
  );

  const filtered = useMemo(() => {
    return logs.filter((log) => {
      if (levelFilter !== 'all' && log.level.toLowerCase() !== levelFilter) return false;
      if (nsFilter !== 'all' && (log.namespace ?? '') !== nsFilter) return false;
      if (podFilter !== 'all' && (log.pod ?? '') !== podFilter) return false;
      if (searchText) {
        const q = searchText.toLowerCase();
        return log.message.toLowerCase().includes(q) || log.source.toLowerCase().includes(q);
      }
      return true;
    });
  }, [logs, levelFilter, nsFilter, podFilter, searchText]);

  const levelBadge = useCallback((level: string) => {
    const l = level.toLowerCase();
    const cfg: Record<string, string> = {
      error: 'bg-red-500/20 text-red-400',
      warn: 'bg-amber-500/20 text-amber-400',
      warning: 'bg-amber-500/20 text-amber-400',
      info: 'bg-blue-500/20 text-blue-400',
    };
    return (
      <span className={clsx('px-2 py-0.5 rounded text-xs font-mono font-medium', cfg[l] || 'bg-gray-500/20 text-gray-400')}>
        {level.toUpperCase()}
      </span>
    );
  }, []);

  if (logs.length === 0) {
    return (
      <div className="bg-navy-700 border border-navy-600 rounded-xl p-12 text-center text-gray-500">
        <FileText size={40} className="mx-auto mb-3 text-gray-600" />
        <p>No logs to display</p>
      </div>
    );
  }

  return (
    <div className="max-w-screen-2xl space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 bg-navy-800 border border-navy-600 rounded-xl p-4">
        <Filter size={16} className="text-gray-500" />
        <select
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value)}
          aria-label="Filter by log level"
          className="bg-navy-700 border border-navy-600 rounded-lg px-3 py-1.5 text-sm text-gray-300 outline-none focus:border-[#06b6d4]"
        >
          <option value="all">All Levels</option>
          <option value="error">Error</option>
          <option value="warn">Warn</option>
          <option value="info">Info</option>
        </select>
        <select
          value={nsFilter}
          onChange={(e) => setNsFilter(e.target.value)}
          aria-label="Filter by namespace"
          className="bg-navy-700 border border-navy-600 rounded-lg px-3 py-1.5 text-sm text-gray-300 outline-none focus:border-[#06b6d4]"
        >
          {namespaces.map((ns) => (
            <option key={ns} value={ns}>{ns === 'all' ? 'All Namespaces' : ns}</option>
          ))}
        </select>
        <select
          value={podFilter}
          onChange={(e) => setPodFilter(e.target.value)}
          aria-label="Filter by pod"
          className="bg-navy-700 border border-navy-600 rounded-lg px-3 py-1.5 text-sm text-gray-300 outline-none focus:border-[#06b6d4]"
        >
          {pods.map((p) => (
            <option key={p} value={p}>{p === 'all' ? 'All Pods' : p}</option>
          ))}
        </select>
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Search logs..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            aria-label="Search logs"
            className="w-full bg-navy-700 border border-navy-600 rounded-lg pl-9 pr-3 py-1.5 text-sm text-gray-300 outline-none focus:border-[#06b6d4] placeholder-gray-600"
          />
        </div>
        <span className="text-xs text-gray-500">{filtered.length} entries</span>
      </div>

      {/* Log Table */}
      <div className="bg-navy-800 border border-navy-600 rounded-xl overflow-hidden">
        <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-navy-800 z-10">
              <tr className="border-b border-navy-600">
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase w-44">Timestamp</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase w-20">Level</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase w-48">Source</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Message</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((log, idx) => (
                <tr
                  key={`${log.timestamp}-${log.source}-${idx}`}
                  className={clsx(
                    'border-b border-navy-700/50 hover:bg-navy-700/50 transition-colors',
                    idx % 2 === 0 ? 'bg-navy-800' : 'bg-navy-800/70'
                  )}
                >
                  <td className="px-4 py-2 text-xs text-gray-500 font-mono whitespace-nowrap">
                    {(() => {
                      try {
                        return log.timestamp ? format(new Date(log.timestamp), 'MMM d HH:mm:ss.SSS') : '—';
                      } catch {
                        return log.timestamp ?? '—';
                      }
                    })()}
                  </td>
                  <td className="px-4 py-2">{levelBadge(log.level)}</td>
                  <td className="px-4 py-2 text-xs text-gray-400 font-mono truncate max-w-[200px]">{log.source || '—'}</td>
                  <td className="px-4 py-2 text-xs text-gray-300 font-mono">{log.message || '—'}</td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-12 text-center text-gray-500">
                    No logs match the current filters
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

