import { useState, useEffect, useMemo, useCallback, lazy, Suspense } from 'react';
import { useParams, Link } from 'react-router-dom';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import {
  LayoutDashboard,
  AlertTriangle,
  FileText,
  Network,
  Clock,
  Box,
  Search,
  Filter,
  MessageCircle,
  Zap,
  Loader2,
  RefreshCw,
  HelpCircle,
  Sparkles,
  CheckCircle,
  AlertCircle,
} from 'lucide-react';
import { format } from 'date-fns';
import clsx from 'clsx';
import Navbar from '../components/Navbar';
import LoadingSpinner from '../components/LoadingSpinner';
import SeverityBadge from '../components/SeverityBadge';
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
import type { AnalysisResult, BundleInfo, Issue, LogEntry, TimelineEvent, AnalysisHistoryEntry } from '../types';

type Tab = 'overview' | 'issues' | 'cluster-map' | 'logs' | 'chat' | 'log-correlation' | 'timeline';

const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'overview', label: 'Overview', icon: <LayoutDashboard size={18} /> },
  { id: 'issues', label: 'Issues', icon: <AlertTriangle size={18} /> },
  { id: 'cluster-map', label: 'Cluster Map', icon: <Network size={18} /> },
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
      <div className="min-h-screen bg-navy-900">
        <Navbar />
        <div className="flex items-center justify-center h-[80vh]">
          <LoadingSpinner size={40} label="Loading analysis..." />
        </div>
      </div>
    );
  }

  if (error || !analysis) {
    return (
      <div className="min-h-screen bg-navy-900">
        <Navbar />
        <div className="flex flex-col items-center justify-center h-[80vh] gap-4">
          <AlertTriangle size={48} className="text-red-400" />
          <p className="text-gray-400">{error || 'Analysis not found'}</p>
          <Link
            to="/"
            className="mt-2 text-sm text-[#06b6d4] hover:text-cyan-300 transition-colors hover:underline"
          >
            Go back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-navy-900 flex flex-col">
      <Navbar
        bundleName={bundle?.filename}
        bundleId={bundleId}
        onReanalyze={handleReanalyze}
        onExport={handleExport}
        onGeneratePlaybook={() => setPlaybookOpen(true)}
        onGeneratePreflight={() => setPreflightOpen(true)}
        isReanalyzing={isReanalyzing}
      />

      <div className="flex flex-1">
        {/* Left Sidebar */}
        <aside className="w-56 shrink-0 bg-navy-800 border-r border-navy-700 flex flex-col">
          {/* Bundle Info */}
          <div className="p-4 border-b border-navy-700">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-accent-blue/15 rounded-xl flex items-center justify-center">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-accent-blue">
                  <path d="M12 2L2 7l10 5 10-5-10-5z" />
                  <path d="M2 17l10 5 10-5" />
                  <path d="M2 12l10 5 10-5" />
                </svg>
              </div>
              <div className="min-w-0">
                <p className="text-sm font-bold text-white truncate">{bundle?.filename?.replace('.tar.gz', '') || 'Bundle'}</p>
                <p className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">Health Score: {analysis.cluster_health.score}</p>
              </div>
            </div>
          </div>

          {/* Navigation */}
          <div className="flex-1 py-4 px-2">
            <p className="px-4 mb-2 text-[10px] font-semibold text-gray-600 uppercase tracking-widest">Analysis Hub</p>
            <div className="space-y-0.5">
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
          </div>

          {/* Bottom Actions */}
          <div className="p-3 space-y-3 border-t border-navy-700">
            <button
              onClick={handleReanalyze}
              disabled={isReanalyzing}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-accent-blue hover:bg-blue-600 text-white text-xs font-bold uppercase tracking-wider rounded-lg transition-colors disabled:opacity-50"
            >
              {isReanalyzing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              Re-analyze Bundle
            </button>

            <div className="space-y-0.5">
              <button className="sidebar-item sidebar-item-inactive w-full">
                <FileText size={16} />
                Docs
              </button>
              <button className="sidebar-item sidebar-item-inactive w-full">
                <HelpCircle size={16} />
                Support
              </button>
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Top Tab Bar */}
          <div className="bg-navy-800 border-b border-navy-700 px-6 flex items-center justify-between">
            <div className="flex items-center gap-0">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={clsx(
                    'px-5 py-3.5 text-sm font-medium border-b-2 transition-colors',
                    activeTab === tab.id
                      ? 'text-white border-accent-blue'
                      : 'text-gray-400 border-transparent hover:text-gray-200'
                  )}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPlaybookOpen(true)}
                className="px-3 py-1.5 text-xs font-medium text-gray-300 bg-navy-700 hover:bg-navy-600 rounded-lg transition-colors"
              >
                Export PDF
              </button>
              <button
                onClick={handleExport}
                className="px-3 py-1.5 text-xs font-medium text-white bg-navy-700 hover:bg-navy-600 border border-navy-600 rounded-lg transition-colors"
              >
                Share Report
              </button>
            </div>
          </div>

          {/* Tab Content */}
          <main className="flex-1 p-6 overflow-auto">
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
            {activeTab === 'timeline' && <TimelineTab events={analysis.raw_events} />}
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

  return (
    <div className="flex gap-6 max-w-screen-2xl">
      {/* Left Column - Health Metrics */}
      <div className="w-[340px] shrink-0 space-y-5">
        {/* Cluster Health */}
        <div className="bg-navy-800 border border-navy-700 rounded-xl p-6">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-6">Cluster Health</h3>
          <div className="flex justify-center">
            <HealthScore score={health.score} size={200} trend={historyData.length > 1 ? historyData.map(h => h.health_score) : undefined} />
          </div>
          <div className="mt-6 pt-4 border-t border-navy-700">
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-500 uppercase tracking-wider">Analyzed Pods</span>
              <span className="text-sm font-bold text-white">{health.pod_count}</span>
            </div>
          </div>
        </div>

        {/* AI Insight */}
        {summary && (
          <div className="bg-navy-800 border border-navy-700 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles size={16} className="text-accent-blue" />
              <span className="text-xs font-semibold text-accent-blue uppercase tracking-wider">AI Insight</span>
            </div>
            <p className="text-sm text-gray-400 italic leading-relaxed">&ldquo;{summary.length > 200 ? summary.slice(0, 200) + '...' : summary}&rdquo;</p>
            <div className="flex gap-2 mt-3">
              <span className="text-[10px] px-2 py-0.5 bg-accent-blue/10 text-accent-blue rounded-full font-medium">Optimization</span>
              <span className="text-[10px] px-2 py-0.5 bg-accent-green/10 text-accent-green rounded-full font-medium">Recommended</span>
            </div>
          </div>
        )}

        {/* Severity Summary */}
        <div className="space-y-2">
          <div className="flex items-center justify-between bg-navy-800 border border-navy-700 rounded-xl px-5 py-3.5">
            <div className="flex items-center gap-2">
              <AlertCircle size={16} className="text-red-400" />
              <span className="text-sm text-gray-300">Critical Issues</span>
            </div>
            <span className="text-lg font-bold text-red-400">{health.critical_count}</span>
          </div>
          <div className="flex items-center justify-between bg-navy-800 border border-navy-700 rounded-xl px-5 py-3.5">
            <div className="flex items-center gap-2">
              <AlertTriangle size={16} className="text-amber-400" />
              <span className="text-sm text-gray-300">Warnings</span>
            </div>
            <span className="text-lg font-bold text-amber-400">{health.warning_count}</span>
          </div>
          <div className="flex items-center justify-between bg-navy-800 border border-navy-700 rounded-xl px-5 py-3.5">
            <div className="flex items-center gap-2">
              <CheckCircle size={16} className="text-accent-green" />
              <span className="text-sm text-gray-300">Passed Checks</span>
            </div>
            <span className="text-lg font-bold text-accent-green">{Math.max(0, health.pod_count - health.critical_count - health.warning_count)}</span>
          </div>
        </div>
      </div>

      {/* Right Column - Charts & Findings */}
      <div className="flex-1 space-y-6 min-w-0">
        {/* Charts Row */}
        <div className="grid grid-cols-2 gap-6">
          {/* Severity Distribution - Vertical Bar Chart */}
          <div className="bg-navy-800 border border-navy-700 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-white uppercase tracking-wider">Severity Distribution</h3>
              <span className="text-[10px] text-gray-500">Total Events: {issues.length}</span>
            </div>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={[
                  { name: 'CRITICAL', value: health.critical_count, fill: '#ef4444' },
                  { name: 'WARNING', value: health.warning_count, fill: '#f59e0b' },
                  { name: 'INFO', value: health.info_count, fill: '#3b82f6' },
                ]} barGap={8}>
                  <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#6b7280' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={{ backgroundColor: '#1a2332', border: '1px solid #243044', borderRadius: '8px' }} />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]} barSize={40}>
                    {[
                      { fill: '#ef4444' },
                      { fill: '#f59e0b' },
                      { fill: '#3b82f6' },
                    ].map((entry, index) => (
                      <Cell key={index} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Resource Load - Donut */}
          <div className="bg-navy-800 border border-navy-700 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-white uppercase tracking-wider mb-4">Resource Load</h3>
            <div className="h-48 relative">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={[
                      { name: 'Used', value: health.score },
                      { name: 'Available', value: 100 - health.score },
                    ]}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={75}
                    startAngle={90}
                    endAngle={-270}
                    dataKey="value"
                  >
                    <Cell fill="#f59e0b" />
                    <Cell fill="#1a2332" />
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-2xl font-bold text-white">{health.score}%</span>
                <span className="text-[10px] text-gray-500 uppercase tracking-wider">CPU Used</span>
              </div>
            </div>
            <div className="flex justify-center gap-6 mt-2">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-accent-blue" />
                <span className="text-[10px] text-gray-500">Compute</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-amber-400" />
                <span className="text-[10px] text-gray-500">I/O Wait</span>
              </div>
            </div>
          </div>
        </div>

        {/* Top Critical Findings */}
        <div>
          <h3 className="text-sm font-semibold text-white uppercase tracking-wider mb-4">Top 5 Critical Findings</h3>
          <div className="space-y-3">
            {issues
              .sort((a, b) => {
                const order: Record<string, number> = { critical: 0, warning: 1, info: 2 };
                return (order[a.severity] ?? 3) - (order[b.severity] ?? 3);
              })
              .slice(0, 5)
              .map((issue) => (
                <IssueCard key={issue.id} issue={issue} />
              ))}
          </div>
        </div>

        {/* Export to Playbook */}
        <div className="flex justify-end">
          <button
            onClick={onOpenPlaybook}
            className="flex items-center gap-2 px-6 py-3 bg-accent-blue hover:bg-blue-600 text-white font-semibold rounded-xl transition-all shadow-lg shadow-blue-500/20"
          >
            <Zap size={16} />
            Export to Playbook
          </button>
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

/* ============================================================ */
/* Timeline Tab                                                  */
/* ============================================================ */

function TimelineTab({ events }: { events: TimelineEvent[] }) {
  const [severityFilter, setSeverityFilter] = useState<string>('all');

  const filtered = useMemo(() => {
    const sorted = [...events].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );
    if (severityFilter === 'all') return sorted;
    return sorted.filter((e) => e.severity.toLowerCase() === severityFilter);
  }, [events, severityFilter]);

  const dotColor = (severity: string) => {
    const s = severity.toLowerCase();
    if (s === 'critical' || s === 'error') return 'bg-[#ef4444] shadow-red-400/50';
    if (s === 'warning' || s === 'warn') return 'bg-[#f59e0b] shadow-amber-400/50';
    if (s === 'info') return 'bg-[#06b6d4] shadow-cyan-400/50';
    return 'bg-gray-400';
  };

  if (events.length === 0) {
    return (
      <div className="bg-navy-700 border border-navy-600 rounded-xl p-12 text-center text-gray-500">
        <Clock size={40} className="mx-auto mb-3 text-gray-600" />
        <p>No timeline events available</p>
      </div>
    );
  }

  return (
    <div className="max-w-screen-lg space-y-4">
      {/* Filter */}
      <div className="flex items-center gap-3 bg-navy-800 border border-navy-600 rounded-xl p-4">
        <Filter size={16} className="text-gray-500" />
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          aria-label="Filter timeline by severity"
          className="bg-navy-700 border border-navy-600 rounded-lg px-3 py-1.5 text-sm text-gray-300 outline-none focus:border-[#06b6d4]"
        >
          <option value="all">All Severities</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
        <span className="text-xs text-gray-500">{filtered.length} events</span>
      </div>

      {/* Timeline */}
      <div className="relative pl-8">
        {/* Vertical line */}
        <div className="absolute left-[15px] top-0 bottom-0 w-px bg-navy-600" />

        <div className="space-y-4">
          {filtered.map((event, idx) => (
            <div key={`${event.timestamp}-${event.type}-${idx}`} className="relative flex gap-4">
              {/* Dot */}
              <div
                className={clsx(
                  'absolute left-[-21px] top-4 w-3 h-3 rounded-full shadow-lg ring-4 ring-navy-900',
                  dotColor(event.severity)
                )}
              />

              {/* Card */}
              <div className="flex-1 bg-navy-700 border border-navy-600 rounded-xl p-4 hover:border-navy-500 transition-colors">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <SeverityBadge severity={event.severity} />
                    <span className="text-xs text-gray-500 font-mono">
                      {(() => {
                        try {
                          return format(new Date(event.timestamp), 'MMM d, HH:mm:ss');
                        } catch {
                          return event.timestamp;
                        }
                      })()}
                    </span>
                  </div>
                  <span className="text-xs text-gray-500 bg-navy-800 px-2 py-0.5 rounded">{event.type}</span>
                </div>
                <p className="text-sm text-gray-300">{event.message}</p>
                {event.resource && (
                  <p className="text-xs text-gray-500 mt-1.5 flex items-center gap-1">
                    <Box size={12} />
                    {event.resource}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
