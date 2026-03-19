import { useState, useEffect, useMemo, useCallback, lazy, Suspense } from 'react';
import { useParams } from 'react-router-dom';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, AreaChart, Area, Label } from 'recharts';
import {
  LayoutDashboard,
  AlertTriangle,
  FileText,
  Network,
  Clock,
  Brain,
  Box,
  Layers,
  Search,
  Filter,
  GitBranch,
  MessageCircle,
  X,
  ChevronDown,
  ChevronRight,
  Zap,
  Shield,
  TrendingUp,
  TrendingDown,
  Activity,
} from 'lucide-react';
import { format } from 'date-fns';
import clsx from 'clsx';
import Navbar from '../components/Navbar';
import LoadingSpinner from '../components/LoadingSpinner';
import SeverityBadge from '../components/SeverityBadge';
import IssueCard from '../components/IssueCard';
const ClusterMap = lazy(() => import('../components/ClusterMap'));
import ClusterHealthGrid from '../components/ClusterHealthGrid';
import LogCorrelationView from '../components/LogCorrelationView';
import AIInsightsCard from '../components/AIInsightsCard';
import BundleChat from '../components/BundleChat';
import ErrorBoundary from '../components/ErrorBoundary';
import { PlaybookModal } from '../components/PlaybookExport';
import PreflightViewer from '../components/PreflightViewer';
import { getAnalysis, getBundle, reanalyzeBundle, exportReport, getAnalysisHistory } from '../api/client';
import type { AnalysisResult, BundleInfo, Issue, LogEntry, TimelineEvent, AnalysisHistoryEntry } from '../types';

type Tab = 'overview' | 'issues' | 'log-correlation' | 'logs' | 'cluster-map' | 'timeline';

interface TabDef {
  id: Tab;
  label: string;
  icon: React.ReactNode;
  section: 'analysis' | 'data';
}

const tabs: TabDef[] = [
  { id: 'overview', label: 'Dashboard', icon: <LayoutDashboard size={18} />, section: 'analysis' },
  { id: 'issues', label: 'Detailed Findings', icon: <AlertTriangle size={18} />, section: 'analysis' },
  { id: 'log-correlation', label: 'Log Correlation', icon: <GitBranch size={18} />, section: 'analysis' },
  { id: 'logs', label: 'Log Viewer', icon: <FileText size={18} />, section: 'data' },
  { id: 'cluster-map', label: 'Cluster Map', icon: <Network size={18} />, section: 'data' },
  { id: 'timeline', label: 'Timeline', icon: <Clock size={18} />, section: 'data' },
];

export default function AnalysisView() {
  const { bundleId } = useParams<{ bundleId: string }>();
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [bundle, setBundle] = useState<BundleInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [isReanalyzing, setIsReanalyzing] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
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

  // Compute namespace info from analysis data
  const namespaceInfo = useMemo(() => {
    if (!analysis) return [];
    const nsMap: Record<string, { podCount: number; issueCount: number }> = {};
    analysis.log_entries.forEach((l) => {
      if (l.namespace) {
        if (!nsMap[l.namespace]) nsMap[l.namespace] = { podCount: 0, issueCount: 0 };
      }
    });
    // Count unique pods per namespace from log entries
    const podsByNs: Record<string, Set<string>> = {};
    analysis.log_entries.forEach((l) => {
      if (l.namespace && l.pod) {
        if (!podsByNs[l.namespace]) podsByNs[l.namespace] = new Set();
        podsByNs[l.namespace].add(l.pod);
      }
    });
    // Count issues per namespace
    analysis.issues.forEach((i) => {
      if (i.namespace) {
        if (!nsMap[i.namespace]) nsMap[i.namespace] = { podCount: 0, issueCount: 0 };
        nsMap[i.namespace].issueCount++;
      }
    });
    Object.entries(podsByNs).forEach(([ns, pods]) => {
      if (nsMap[ns]) nsMap[ns].podCount = pods.size;
    });
    return Object.entries(nsMap)
      .map(([name, data]) => ({ name, ...data }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [analysis]);

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
        </div>
      </div>
    );
  }

  const analysisTabs = tabs.filter((t) => t.section === 'analysis');
  const dataTabs = tabs.filter((t) => t.section === 'data');
  const shortBundleId = bundleId ? bundleId.slice(0, 8) : '';

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

      {/* Bundle ID Header Bar */}
      <div className="bg-navy-800 border-b border-navy-600 px-6 py-2.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Shield size={16} className="text-[#06b6d4]" />
          <span className="text-sm font-medium text-gray-200">
            Bundle ID: <span className="font-mono text-[#06b6d4]">#{shortBundleId}</span>
          </span>
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
            Analyzed
          </span>
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider bg-[#06b6d4]/15 text-[#06b6d4] border border-[#06b6d4]/30">
            Troubleshoot.sh
          </span>
        </div>
        <span className="text-xs text-gray-500">
          {analysis.analyzed_at ? (() => { try { return format(new Date(analysis.analyzed_at), 'MMM d, yyyy HH:mm:ss'); } catch { return analysis.analyzed_at; } })() : ''}
        </span>
      </div>

      <div className="flex flex-1">
        {/* Sidebar */}
        <aside className="w-56 shrink-0 bg-navy-800 border-r border-navy-600 min-h-[calc(100vh-6.5rem)] p-3 flex flex-col">
          <p className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">Analysis</p>
          <div className="space-y-1 mb-4">
            {analysisTabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={clsx(
                  'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                  activeTab === tab.id
                    ? 'bg-[#06b6d4]/10 text-[#06b6d4]'
                    : 'text-gray-400 hover:bg-navy-700 hover:text-gray-300'
                )}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>

          <div className="mx-3 border-t border-navy-600 mb-3" />
          <p className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">Data</p>
          <div className="space-y-1">
            {dataTabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={clsx(
                  'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                  activeTab === tab.id
                    ? 'bg-[#06b6d4]/10 text-[#06b6d4]'
                    : 'text-gray-400 hover:bg-navy-700 hover:text-gray-300'
                )}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>

          {/* Namespace Resources Section */}
          {namespaceInfo.length > 0 && (
            <>
              <div className="mx-3 border-t border-navy-600 my-3" />
              <SidebarNamespaces namespaces={namespaceInfo} />
            </>
          )}
        </aside>

        {/* Main Content */}
        <main className="flex-1 p-6 overflow-auto">
          {activeTab === 'overview' && (
            <OverviewTab analysis={analysis} historyData={historyData} onOpenPlaybook={() => setPlaybookOpen(true)} />
          )}
          {activeTab === 'issues' && <IssuesTab issues={analysis.issues} />}
          {activeTab === 'log-correlation' && (
            <ErrorBoundary fallback={
              <div className="bg-navy-800 border border-navy-600 rounded-xl p-8 text-center">
                <p className="text-sm text-gray-400">Log correlation failed to load</p>
                <p className="text-xs text-gray-600 mt-1">Try switching tabs or reloading the page</p>
              </div>
            }>
              <LogCorrelationView correlations={analysis.correlations ?? []} />
            </ErrorBoundary>
          )}
          {activeTab === 'logs' && <LogViewerTab logs={analysis.log_entries} />}
          {activeTab === 'cluster-map' && (
            <div className="space-y-6">
              <ClusterHealthGrid resourceHealth={analysis.resource_health ?? []} />
              <ErrorBoundary fallback={
                <div className="flex items-center justify-center h-[600px] bg-navy-800 rounded-xl border border-navy-600">
                  <div className="text-center space-y-3">
                    <p className="text-sm text-gray-400">3D visualization unavailable</p>
                    <p className="text-xs text-gray-600">WebGL may not be supported in this browser</p>
                  </div>
                </div>
              }>
                <Suspense fallback={
                  <div className="flex items-center justify-center h-[600px] bg-navy-800 rounded-xl border border-navy-600">
                    <div className="text-center space-y-3">
                      <div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mx-auto" />
                      <p className="text-sm text-gray-500">Loading 3D topology...</p>
                    </div>
                  </div>
                }>
                  <ClusterMap nodes={analysis.topology_nodes} edges={analysis.topology_edges} />
                </Suspense>
              </ErrorBoundary>
            </div>
          )}
          {activeTab === 'timeline' && <TimelineTab events={analysis.raw_events} />}
        </main>

        {/* Chat Panel */}
        {chatOpen && bundleId && (
          <ErrorBoundary fallback={
            <div className="w-96 shrink-0 bg-navy-800 border-l border-navy-600 flex items-center justify-center h-[calc(100vh-3.5rem)]">
              <div className="text-center p-6">
                <p className="text-sm text-gray-400">Chat unavailable</p>
                <p className="text-xs text-gray-600 mt-1">Please try again later</p>
              </div>
            </div>
          }>
            <BundleChat bundleId={bundleId} />
          </ErrorBoundary>
        )}
      </div>

      {/* Bottom Status Bar */}
      <div className="bg-navy-800 border-t border-navy-600 px-6 py-1.5 flex items-center justify-between text-[11px] font-mono text-gray-500 shrink-0">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            AI ENGINE: ACTIVE
          </span>
        </div>
        <div className="flex items-center gap-4">
          <span>PROCESSING ID: {bundleId ?? 'N/A'}</span>
          <span>
            {analysis.analyzed_at ? (() => { try { return format(new Date(analysis.analyzed_at), 'yyyy-MM-dd HH:mm:ss'); } catch { return ''; } })() : ''}
          </span>
        </div>
      </div>

      {/* Floating Chat Toggle Button */}
      <button
        onClick={() => setChatOpen((prev) => !prev)}
        aria-label={chatOpen ? 'Close chat panel' : 'Open chat panel'}
        className={clsx(
          'fixed bottom-12 right-6 z-50 flex items-center gap-2 px-4 py-2.5 rounded-full shadow-lg transition-colors',
          chatOpen
            ? 'bg-navy-700 border border-navy-500 text-gray-300 hover:bg-navy-600'
            : 'bg-[#06b6d4] hover:bg-cyan-600 text-white'
        )}
      >
        {chatOpen ? <X size={16} /> : <MessageCircle size={16} />}
        <span className="text-sm font-medium">{chatOpen ? 'Close' : 'Chat'}</span>
      </button>

      {/* Playbook Modal */}
      {playbookOpen && (
        <PlaybookModal
          analysis={analysis}
          bundleFilename={bundle?.filename}
          onClose={() => setPlaybookOpen(false)}
        />
      )}

      {/* Preflight Viewer Modal */}
      {preflightOpen && bundleId && (
        <PreflightViewer
          bundleId={bundleId}
          onClose={() => setPreflightOpen(false)}
        />
      )}
    </div>
  );
}

/* ============================================================ */
/* Sidebar Namespaces Section                                    */
/* ============================================================ */

function SidebarNamespaces({
  namespaces,
}: {
  namespaces: { name: string; podCount: number; issueCount: number }[];
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500 hover:text-gray-400 transition-colors"
      >
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        Resources
      </button>
      {expanded && (
        <div className="space-y-0.5 ml-2">
          {namespaces.map((ns) => (
            <div
              key={ns.name}
              className="flex items-center justify-between px-3 py-1.5 rounded text-xs text-gray-400"
            >
              <div className="flex items-center gap-2 min-w-0">
                <Layers size={12} className="text-gray-500 shrink-0" />
                <span className="truncate">{ns.name}</span>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {ns.issueCount > 0 && (
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400" title={`${ns.issueCount} issues`} />
                )}
                <span className="text-[10px] text-gray-500">{ns.podCount}p</span>
              </div>
            </div>
          ))}
        </div>
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

  // Build sorted timeline from issues + raw_events
  const timelineEntries = useMemo(() => {
    const entries: {
      id: string;
      timestamp: string;
      severity: string;
      title: string;
      description: string;
    }[] = [];

    // Add issues as timeline entries (use analyzed_at as fallback timestamp)
    issues.forEach((issue) => {
      entries.push({
        id: issue.id,
        timestamp: analysis.analyzed_at,
        severity: issue.severity,
        title: issue.title,
        description: issue.description,
      });
    });

    // Add raw events
    analysis.raw_events?.forEach((event, idx) => {
      entries.push({
        id: `event-${idx}`,
        timestamp: event.timestamp,
        severity: event.severity,
        title: event.type,
        description: event.message,
      });
    });

    // Sort by time descending (most recent first)
    entries.sort((a, b) => {
      try {
        return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
      } catch {
        return 0;
      }
    });

    return entries.slice(0, 12);
  }, [issues, analysis.raw_events, analysis.analyzed_at]);

  // Build AI diagnostic cards from issues
  const diagnosticCards = useMemo(() => {
    const order: Record<string, number> = { critical: 0, warning: 1, info: 2 };
    return [...issues]
      .sort((a, b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3))
      .slice(0, 6)
      .map((issue) => ({
        id: issue.id,
        severity: issue.severity,
        category: issue.category?.toUpperCase() ?? 'UNKNOWN',
        description: issue.title,
      }));
  }, [issues]);

  const [expandedTimelineId, setExpandedTimelineId] = useState<string | null>(null);

  const severityDotColor = (severity: string) => {
    const s = severity?.toLowerCase();
    if (s === 'critical' || s === 'error') return 'bg-[#ef4444]';
    if (s === 'warning' || s === 'warn') return 'bg-[#f59e0b]';
    if (s === 'info') return 'bg-[#06b6d4]';
    return 'bg-gray-400';
  };

  const severityBorderColor = (severity: string) => {
    const s = severity?.toLowerCase();
    if (s === 'critical' || s === 'error') return 'border-l-[#ef4444]';
    if (s === 'warning' || s === 'warn') return 'border-l-[#f59e0b]';
    if (s === 'info') return 'border-l-[#06b6d4]';
    return 'border-l-gray-400';
  };

  return (
    <div className="space-y-6 max-w-screen-xl">
      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-4">
        <StatCardNew
          label="SYSTEM HEALTH"
          value={`${health.score}%`}
          color="#06b6d4"
          progress={health.score}
          subtitle={health.score > 70 ? 'Healthy' : health.score > 40 ? 'Degraded' : 'Critical'}
        />
        <StatCardNew
          label="CRITICAL ISSUES"
          value={String(health.critical_count)}
          color="#ef4444"
          progress={health.critical_count > 0 ? Math.min(100, health.critical_count * 20) : 0}
          subtitle={`across ${health.namespace_count} namespaces`}
          trend={health.critical_count > 0 ? 'up' : undefined}
        />
        <StatCardNew
          label="WARNINGS"
          value={String(health.warning_count)}
          color="#f59e0b"
          progress={health.warning_count > 0 ? Math.min(100, health.warning_count * 15) : 0}
          subtitle={`${health.pod_count} pods monitored`}
          trend={health.warning_count > 0 ? 'up' : undefined}
        />
        <StatCardNew
          label="LOG VOLUME"
          value={String(analysis.log_entries?.length ?? 0)}
          color="#06b6d4"
          progress={Math.min(100, ((analysis.log_entries?.length ?? 0) / 200) * 100)}
          subtitle="entries analyzed"
          valueLabel="entries"
        />
      </div>

      {/* Health Trend + Issue Breakdown Row */}
      {historyData.length > 1 && (
        <div className="bg-navy-800 border border-navy-700 rounded-xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-8 h-8 bg-[#06b6d4]/20 rounded-lg flex items-center justify-center">
              <Activity size={18} className="text-[#06b6d4]" />
            </div>
            <h3 className="text-base font-semibold text-white">Health Score Trend</h3>
            <span className="text-xs text-gray-500 ml-2">{historyData.length} analysis runs</span>
          </div>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={historyData.map((h, i) => ({
                run: `Run ${i + 1}`,
                score: h.health_score,
                critical: h.critical_count,
                warning: h.warning_count,
                time: (() => { try { return format(new Date(h.analyzed_at), 'MMM d HH:mm'); } catch { return `Run ${i+1}`; } })(),
              }))}>
                <defs>
                  <linearGradient id="healthGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#6b7280' }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#6b7280' }} axisLine={false} tickLine={false} width={30}>
                  <Label value="Score %" position="insideTopLeft" offset={-5} style={{ fontSize: 9, fill: '#6b7280' }} />
                </YAxis>
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const d = payload[0].payload;
                    return (
                      <div className="bg-navy-800 border border-navy-600 rounded-lg px-3 py-2 text-xs shadow-xl">
                        <p className="text-white font-semibold mb-1">Health: {d.score}%</p>
                        <p className="text-red-400">Critical: {d.critical}</p>
                        <p className="text-amber-400">Warning: {d.warning}</p>
                        <p className="text-gray-500 mt-1">{d.time}</p>
                      </div>
                    );
                  }}
                />
                <Area type="monotone" dataKey="score" stroke="#06b6d4" fill="url(#healthGradient)" strokeWidth={2} dot={{ fill: '#06b6d4', strokeWidth: 0, r: 3 }} activeDot={{ r: 5, fill: '#06b6d4', stroke: '#0a0e1a', strokeWidth: 2 }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Visual Breakdown Charts */}
      <AnalysisCharts analysis={analysis} />

      {/* AI Insights */}
      {(analysis.ai_insights?.length ?? 0) > 0 && (
        <AIInsightsCard insights={analysis.ai_insights ?? []} />
      )}

      {/* Two-column layout: Signal Correlation Timeline + AI Diagnostic Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Left column (60%) - Signal Correlation Timeline */}
        <div className="lg:col-span-3 bg-navy-800 border border-navy-700 rounded-xl p-6" style={{ boxShadow: '0 0 30px rgba(6,182,212,0.04)' }}>
          <div className="flex items-center gap-2 mb-5">
            <div className="w-8 h-8 bg-[#06b6d4]/20 rounded-lg flex items-center justify-center" style={{ boxShadow: '0 0 12px rgba(6,182,212,0.2)' }}>
              <Clock size={18} className="text-[#06b6d4]" />
            </div>
            <h3 className="text-base font-semibold text-white">Signal Correlation Timeline</h3>
          </div>

          {timelineEntries.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-8">No events recorded</p>
          ) : (
            <div className="relative pl-6">
              {/* Vertical line */}
              <div className="absolute left-[7px] top-0 bottom-0 w-px bg-navy-500" />

              <div className="space-y-3">
                {timelineEntries.map((entry) => {
                  const isExpanded = expandedTimelineId === entry.id;
                  return (
                    <button
                      key={entry.id}
                      onClick={() => setExpandedTimelineId(isExpanded ? null : entry.id)}
                      className="relative flex gap-3 w-full text-left group"
                    >
                      {/* Dot */}
                      <div
                        className={clsx(
                          'absolute left-[-20px] top-3 w-2.5 h-2.5 rounded-full ring-2 ring-navy-700',
                          severityDotColor(entry.severity)
                        )}
                      />

                      {/* Card */}
                      <div className="flex-1 bg-navy-800 border border-navy-600 rounded-lg p-3 group-hover:border-navy-500 transition-colors">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-[10px] font-mono text-gray-500">
                            {(() => { try { return format(new Date(entry.timestamp), 'HH:mm:ss'); } catch { return '--:--:--'; } })()}
                          </span>
                          <SeverityBadge severity={entry.severity} />
                        </div>
                        <p className="text-sm text-gray-200 font-medium">{entry.title}</p>
                        {isExpanded && (
                          <p className="text-xs text-gray-400 mt-1.5 leading-relaxed">{entry.description}</p>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Right column (40%) - AI Diagnostic Summary */}
        <div className="lg:col-span-2 space-y-6">
          {/* AI Summary */}
          {summary && (
            <div className="bg-navy-800 border border-navy-700 rounded-xl p-6" style={{ boxShadow: '0 0 30px rgba(139,92,246,0.04)' }}>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 bg-[#8b5cf6]/20 rounded-lg flex items-center justify-center" style={{ boxShadow: '0 0 12px rgba(139,92,246,0.2)' }}>
                  <Brain size={18} className="text-[#8b5cf6]" />
                </div>
                <h3 className="text-base font-semibold text-white">AI Diagnostic Summary</h3>
              </div>
              <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-line">{summary}</p>
            </div>
          )}

          {/* AI Diagnostic Cards */}
          {diagnosticCards.length > 0 && (
            <div className="space-y-2">
              {diagnosticCards.map((card) => (
                <div
                  key={card.id}
                  className={clsx(
                    'bg-navy-700 border border-navy-600 rounded-lg p-3 border-l-4 transition-colors hover:border-navy-500',
                    severityBorderColor(card.severity)
                  )}
                >
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                    {card.category}
                  </span>
                  <p className="text-sm text-gray-300 mt-0.5">{card.description}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Cluster Health Grid */}
      <ClusterHealthGrid resourceHealth={analysis.resource_health ?? []} />

      {/* Generate Resolution Steps */}
      <div className="flex justify-center">
        <button
          onClick={onOpenPlaybook}
          className="flex items-center gap-2 px-8 py-3.5 bg-[#8b5cf6] hover:bg-[#7c3aed] text-white font-semibold rounded-xl transition-all duration-200 shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 hover:scale-[1.02]"
        >
          <Zap size={18} />
          GENERATE RESOLUTION STEPS
        </button>
      </div>
    </div>
  );
}

/* ============================================================ */
/* Analysis Charts                                              */
/* ============================================================ */

const POD_STATUS_COLORS: Record<string, string> = {
  Running: '#10b981', Succeeded: '#06b6d4', Pending: '#f59e0b',
  Failed: '#ef4444', CrashLoopBackOff: '#ef4444', Unknown: '#6b7280',
  ImagePullBackOff: '#f97316', OOMKilled: '#dc2626', Error: '#ef4444',
  Evicted: '#9333ea', ContainerCreating: '#3b82f6',
  Healthy: '#10b981', Critical: '#ef4444', Warning: '#f59e0b',
  Ready: '#10b981', healthy: '#10b981', critical: '#ef4444', warning: '#f59e0b',
  running: '#10b981', error: '#ef4444', pending: '#f59e0b', unknown: '#6b7280',
};

function AnalysisCharts({ analysis }: { analysis: AnalysisResult }) {
  const { issues, cluster_health: h, log_entries, resource_health } = analysis;

  // Pod status distribution
  const podStatusData = useMemo(() => {
    const counts: Record<string, number> = {};
    (resource_health ?? []).forEach(r => {
      if ((r.type ?? '').toLowerCase() === 'pod') {
        const s = (r.status ?? 'Unknown').charAt(0).toUpperCase() + (r.status ?? 'Unknown').slice(1);
        counts[s] = (counts[s] || 0) + 1;
      }
    });
    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  }, [resource_health]);

  // Issue severity breakdown
  const severityData = useMemo(() => [
    { name: 'Critical', value: h.critical_count, color: '#ef4444' },
    { name: 'Warning', value: h.warning_count, color: '#f59e0b' },
    { name: 'Info', value: h.info_count, color: '#06b6d4' },
  ].filter(d => d.value > 0), [h]);

  // Issue category distribution
  const categoryData = useMemo(() => {
    const counts: Record<string, number> = {};
    issues.forEach(i => { counts[i.category] = (counts[i.category] || 0) + 1; });
    return Object.entries(counts)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 6);
  }, [issues]);

  // Log level distribution
  const logLevelData = useMemo(() => {
    const counts: Record<string, number> = { error: 0, warn: 0, info: 0 };
    (log_entries ?? []).forEach(l => { const lv = (l.level ?? 'info').toLowerCase(); counts[lv] = (counts[lv] || 0) + 1; });
    return [
      { name: 'Error', value: counts.error, color: '#ef4444' },
      { name: 'Warn', value: counts.warn, color: '#f59e0b' },
      { name: 'Info', value: counts.info, color: '#06b6d4' },
    ].filter(d => d.value > 0);
  }, [log_entries]);

  const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: Array<{ name: string; value: number }> }) => {
    if (!active || !payload?.length) return null;
    return (
      <div className="bg-navy-800 border border-navy-600 rounded-lg px-3 py-2 text-xs shadow-xl">
        <p className="text-gray-300 font-medium">{payload[0].name}: <span className="text-white">{payload[0].value}</span></p>
      </div>
    );
  };

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {/* Pod Status Distribution */}
      <div className="bg-navy-800 border border-navy-700 rounded-xl p-4">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-3">Pod Status</p>
        <div className="h-36">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={podStatusData} cx="50%" cy="50%" innerRadius={30} outerRadius={55} paddingAngle={2} dataKey="value" animationDuration={800} animationBegin={100}>
                {podStatusData.map((entry) => (
                  <Cell key={entry.name} fill={POD_STATUS_COLORS[entry.name] ?? '#6b7280'} />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 justify-center">
          {podStatusData.map(d => (
            <div key={d.name} className="flex items-center gap-1 text-[10px] text-gray-400">
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: POD_STATUS_COLORS[d.name] ?? '#6b7280' }} />
              {d.name} ({d.value})
            </div>
          ))}
        </div>
      </div>

      {/* Severity Breakdown */}
      <div className="bg-navy-800 border border-navy-700 rounded-xl p-4">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-3">Issue Severity</p>
        <div className="h-36">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={severityData} cx="50%" cy="50%" innerRadius={30} outerRadius={55} paddingAngle={2} dataKey="value" animationDuration={800} animationBegin={100}>
                {severityData.map((entry) => (
                  <Cell key={entry.name} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 justify-center">
          {severityData.map(d => (
            <div key={d.name} className="flex items-center gap-1 text-[10px] text-gray-400">
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: d.color }} />
              {d.name} ({d.value})
            </div>
          ))}
        </div>
      </div>

      {/* Issue Categories Bar Chart */}
      <div className="bg-navy-800 border border-navy-700 rounded-xl p-4">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-3">Issue Categories</p>
        <div className="h-40">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={categoryData} layout="vertical" margin={{ left: 0, right: 8, top: 4, bottom: 4 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 9, fill: '#9ca3af' }} width={80} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="value" fill="#06b6d4" radius={[0, 4, 4, 0]} barSize={12} animationDuration={800} label={{ position: 'right', fill: '#9ca3af', fontSize: 10 }} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Log Level Distribution */}
      <div className="bg-navy-800 border border-navy-700 rounded-xl p-4">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-3">Log Levels</p>
        <div className="h-36">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={logLevelData} cx="50%" cy="50%" innerRadius={30} outerRadius={55} paddingAngle={2} dataKey="value" animationDuration={800} animationBegin={100}>
                {logLevelData.map((entry) => (
                  <Cell key={entry.name} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 justify-center">
          {logLevelData.map(d => (
            <div key={d.name} className="flex items-center gap-1 text-[10px] text-gray-400">
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: d.color }} />
              {d.name} ({d.value})
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCardNew({
  label,
  value,
  color,
  progress,
  subtitle,
  trend,
  valueLabel,
  onClick,
}: {
  label: string;
  value: string;
  color: string;
  progress: number;
  subtitle?: string;
  trend?: 'up' | 'down';
  valueLabel?: string;
  onClick?: () => void;
}) {
  return (
    <div
      className={clsx(
        "bg-navy-800 border border-navy-700 rounded-xl p-5 transition-all duration-300 hover:border-opacity-60",
        onClick && "cursor-pointer hover:scale-[1.02]"
      )}
      style={{ borderColor: `${color}25`, boxShadow: `0 0 20px ${color}08` }}
      onClick={onClick}
    >
      <div className="flex items-center justify-between mb-1">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">{label}</p>
        {trend && (
          <span className="flex items-center gap-0.5 text-[10px] font-bold" style={{ color, textShadow: `0 0 8px ${color}80` }}>
            {trend === 'up' ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
            {trend === 'up' ? '▲' : '▼'}
          </span>
        )}
      </div>
      <div className="flex items-baseline gap-1.5 mb-3">
        <p
          className="text-4xl font-bold tracking-tight"
          style={{ color, textShadow: `0 0 20px ${color}40` }}
        >
          {value}
        </p>
        {valueLabel && <span className="text-xs text-gray-500">{valueLabel}</span>}
      </div>
      {/* Progress bar */}
      <div className="w-full h-1.5 bg-navy-900 rounded-full overflow-hidden mb-2">
        <div
          className="h-full rounded-full transition-all duration-1000 ease-out"
          style={{
            width: `${Math.min(100, progress)}%`,
            backgroundColor: color,
            boxShadow: `0 0 8px ${color}60`,
          }}
        />
      </div>
      {subtitle && <p className="text-[10px] text-gray-500">{subtitle}</p>}
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
      if (nsFilter !== 'all' && log.namespace !== nsFilter) return false;
      if (podFilter !== 'all' && log.pod !== podFilter) return false;
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
                  <td className="px-4 py-2 text-xs text-gray-400 font-mono truncate max-w-[200px]">{log.source}</td>
                  <td className="px-4 py-2 text-xs text-gray-300 font-mono">{log.message}</td>
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
