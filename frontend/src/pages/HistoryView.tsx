import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import { History, ArrowRight, GitCompare, ChevronDown, ChevronRight, AlertCircle } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import clsx from 'clsx';
import Navbar from '../components/Navbar';
import LoadingSpinner from '../components/LoadingSpinner';
import { getBundles, getAnalysis, getAnalysisHistory } from '../api/client';
import type { BundleInfo, AnalysisResult, AnalysisHistoryEntry } from '../types';

interface BundleWithAnalysis {
  bundle: BundleInfo;
  analysis: AnalysisResult | null;
  history: AnalysisHistoryEntry[];
  expanded: boolean;
}

export default function HistoryView() {
  const navigate = useNavigate();
  const [items, setItems] = useState<BundleWithAnalysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'critical' | 'stable'>('all');

  const load = useCallback(async () => {
    try {
      const bundles = await getBundles();
      const results: BundleWithAnalysis[] = [];
      for (const bundle of bundles) {
        let analysis: AnalysisResult | null = null;
        let history: AnalysisHistoryEntry[] = [];
        if (bundle.status === 'completed') {
          try {
            analysis = await getAnalysis(bundle.id);
          } catch (e) { console.warn(`Failed to load analysis for ${bundle.id}:`, e); }
          try {
            history = await getAnalysisHistory(bundle.id);
          } catch (e) { console.warn(`Failed to load history for ${bundle.id}:`, e); }
        }
        results.push({ bundle, analysis, history, expanded: false });
      }
      setItems(results);
    } catch {
      setError('Failed to load history.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggleExpand = (id: string) => {
    setItems(prev => prev.map(item =>
      item.bundle.id === id ? { ...item, expanded: !item.expanded } : item
    ));
  };

  const toggleSelect = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < 2) next.add(id);
      return next;
    });
  };

  const handleCompare = () => {
    const ids = Array.from(selected);
    if (ids.length === 2) {
      navigate(`/compare?left=${ids[0]}&right=${ids[1]}`);
    }
  };

  return (
    <div className="min-h-screen bg-navy-900">
      <Navbar />
      <main className="max-w-screen-xl mx-auto px-8 py-8 space-y-8">

        {/* Health Performance Trend */}
        {items.some(i => i.analysis) && (
          <div className="bg-navy-800 border border-navy-700 rounded-xl p-6">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-xl font-bold text-white">Health Performance Trend</h2>
                <p className="text-xs text-gray-500 uppercase tracking-wider mt-1">Aggregate bundle scores over time</p>
              </div>
              {items.filter(i => i.analysis).length > 0 && (
                <div className="text-right">
                  <p className="text-4xl font-bold text-white">
                    {Math.round(items.filter(i => i.analysis).reduce((sum, i) => sum + (i.analysis?.cluster_health.score ?? 0), 0) / items.filter(i => i.analysis).length)}
                  </p>
                  <p className="text-xs text-accent-green">avg score</p>
                </div>
              )}
            </div>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={items.filter(i => i.analysis).map((item, idx) => ({
                  name: item.bundle.filename?.slice(0, 15) || `Bundle ${idx + 1}`,
                  score: item.analysis?.cluster_health.score ?? 0,
                }))}>
                  <defs>
                    <linearGradient id="histGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#6b7280' }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#6b7280' }} axisLine={false} tickLine={false} width={30} />
                  <Tooltip contentStyle={{ backgroundColor: '#1a2332', border: '1px solid #243044', borderRadius: '8px', fontSize: '12px' }} />
                  <Area type="monotone" dataKey="score" stroke="#3b82f6" fill="url(#histGradient)" strokeWidth={2} dot={{ fill: '#3b82f6', r: 4 }} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Header with compare button */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-white">Analysis History</h2>
            <p className="text-xs text-gray-500">Review and compare past bundle analyses</p>
          </div>
          <div className="flex items-center gap-3">
            {selected.size === 1 && (
              <span className="text-xs text-gray-400 bg-navy-800 px-3 py-1.5 rounded-lg border border-navy-700">Select one more to compare</span>
            )}
            {selected.size === 2 && (
              <button onClick={handleCompare} className="flex items-center gap-2 px-4 py-2 bg-accent-blue hover:bg-blue-600 text-white text-sm font-semibold rounded-lg transition-colors">
                <GitCompare size={16} />
                Compare Selected
              </button>
            )}
            {/* Filter buttons */}
            <div className="flex items-center gap-1 bg-navy-800 border border-navy-700 rounded-lg p-0.5">
              <button onClick={() => setFilter('all')} className={clsx('px-3 py-1 text-xs font-medium rounded-md', filter === 'all' ? 'text-white bg-navy-700' : 'text-gray-400 hover:text-gray-200')}>All</button>
              <button onClick={() => setFilter('critical')} className={clsx('px-3 py-1 text-xs font-medium rounded-md', filter === 'critical' ? 'text-white bg-navy-700' : 'text-gray-400 hover:text-gray-200')}>Critical</button>
              <button onClick={() => setFilter('stable')} className={clsx('px-3 py-1 text-xs font-medium rounded-md', filter === 'stable' ? 'text-white bg-navy-700' : 'text-gray-400 hover:text-gray-200')}>Stable</button>
            </div>
          </div>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-center gap-3">
            <AlertCircle size={18} className="text-red-400 shrink-0" />
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {loading ? (
          <LoadingSpinner size={32} label="Loading history..." className="py-16" />
        ) : items.length === 0 ? (
          <div className="bg-navy-800/50 border border-navy-700 rounded-xl p-12 text-center">
            <History size={36} className="text-gray-700 mx-auto mb-3" />
            <p className="text-gray-500 text-sm">No bundles found</p>
          </div>
        ) : (
          <div className="space-y-3">
            {items.filter(item => {
              if (filter === 'critical') return (item.analysis?.cluster_health.critical_count ?? 0) > 0;
              if (filter === 'stable') return item.analysis !== null && (item.analysis.cluster_health.critical_count ?? 0) === 0;
              return true;
            }).map(({ bundle, analysis, history, expanded }) => (
              <div key={bundle.id} className="bg-navy-800 border border-navy-700 rounded-xl overflow-hidden hover:border-navy-600 transition-colors">
                <div className="p-5 flex items-center gap-5">
                  {/* Checkbox */}
                  <label className="shrink-0">
                    <input
                      type="checkbox"
                      checked={selected.has(bundle.id)}
                      onChange={() => toggleSelect(bundle.id)}
                      disabled={!analysis || (!selected.has(bundle.id) && selected.size >= 2)}
                      className="w-4 h-4 rounded border-navy-600 bg-navy-700 text-accent-blue focus:ring-accent-blue focus:ring-offset-0 disabled:opacity-30"
                    />
                  </label>

                  {/* Date/time block */}
                  <div className="shrink-0 text-right w-20">
                    <p className="text-xs text-gray-500 uppercase">
                      {(() => { try { return format(new Date(bundle.upload_time), 'MMM d'); } catch { return ''; } })()}
                    </p>
                    <p className="text-lg font-bold text-gray-300">
                      {(() => { try { return format(new Date(bundle.upload_time), 'HH:mm'); } catch { return '--:--'; } })()}
                    </p>
                  </div>

                  {/* Health score circle */}
                  {analysis && (
                    <div className="shrink-0">
                      <div className={clsx(
                        'w-12 h-12 rounded-full flex items-center justify-center text-sm font-bold border-2',
                        analysis.cluster_health.score > 70 ? 'border-accent-green/50 text-accent-green bg-accent-green/10' :
                        analysis.cluster_health.score > 40 ? 'border-amber-400/50 text-amber-400 bg-amber-400/10' :
                        'border-red-400/50 text-red-400 bg-red-400/10'
                      )}>
                        {analysis.cluster_health.score}
                      </div>
                    </div>
                  )}

                  {/* Bundle info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-gray-200 truncate">{bundle.filename}</p>
                      {analysis && analysis.cluster_health.critical_count > 0 && (
                        <span className="px-2 py-0.5 text-[10px] font-bold uppercase bg-red-500/15 text-red-400 rounded">Critical</span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {analysis ? `${analysis.issues.length} issues found` : 'Not analyzed'}
                      {analysis?.cluster_health.critical_count === 0 && analysis ? ' \u00b7 No critical regressions' : ''}
                    </p>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-3 shrink-0">
                    {analysis && (
                      <button
                        onClick={() => navigate(`/analysis/${bundle.id}`)}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-accent-blue hover:bg-accent-blue/10 rounded-lg transition-colors"
                      >
                        View <ArrowRight size={12} />
                      </button>
                    )}
                    {history.length > 0 && (
                      <button
                        onClick={() => toggleExpand(bundle.id)}
                        className="p-1.5 text-gray-500 hover:text-gray-300 hover:bg-navy-700 rounded-lg transition-colors"
                      >
                        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                      </button>
                    )}
                  </div>
                </div>

                {/* Expanded history */}
                {expanded && history.length > 0 && (
                  <div className="border-t border-navy-700 bg-navy-800/50 px-5 py-3">
                    <p className="text-xs font-medium text-gray-500 mb-2 uppercase tracking-wide">Analysis Runs</p>
                    <div className="space-y-1.5">
                      {history.map((entry, i) => (
                        <div key={i} className="flex items-center justify-between py-2 px-3 bg-navy-700/50 rounded-lg text-xs">
                          <div className="flex items-center gap-3">
                            <span className={clsx('font-bold text-sm',
                              entry.health_score > 70 ? 'text-accent-green' :
                              entry.health_score > 40 ? 'text-amber-400' : 'text-red-400'
                            )}>
                              {entry.health_score}%
                            </span>
                            <span className="text-gray-400">
                              {(() => { try { return format(new Date(entry.analyzed_at), 'MMM d, yyyy HH:mm:ss'); } catch { return entry.analyzed_at; } })()}
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-red-400">{entry.critical_count} critical</span>
                            <span className="text-amber-400">{entry.warning_count} warning</span>
                            <span className="text-blue-400">{entry.info_count} info</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
