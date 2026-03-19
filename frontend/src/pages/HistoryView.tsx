import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import { History, ArrowRight, GitCompare, ChevronDown, ChevronRight, AlertTriangle, AlertCircle, Info } from 'lucide-react';
import clsx from 'clsx';
import Navbar from '../components/Navbar';
import HealthScore from '../components/HealthScore';
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
      <main className="max-w-screen-lg mx-auto px-6 py-10 space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-[#8b5cf6]/10 rounded-xl flex items-center justify-center">
              <History size={20} className="text-[#8b5cf6]" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">Analysis History</h1>
              <p className="text-xs text-gray-500">Compare and review past bundle analyses</p>
            </div>
          </div>
          {selected.size === 2 && (
            <button
              onClick={handleCompare}
              className="flex items-center gap-2 px-4 py-2 bg-[#8b5cf6] hover:bg-violet-600 text-white text-sm font-semibold rounded-xl transition-all shadow-lg shadow-violet-500/20"
            >
              <GitCompare size={16} />
              Compare Selected
            </button>
          )}
        </div>

        {selected.size === 1 && (
          <div className="bg-violet-500/10 border border-violet-500/30 rounded-xl p-3 text-sm text-violet-300">
            Select one more bundle to compare
          </div>
        )}

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
            {items.map(({ bundle, analysis, history, expanded }) => (
              <div key={bundle.id} className="bg-navy-800 border border-navy-700 rounded-xl overflow-hidden">
                <div className="p-4 flex items-center gap-4">
                  {/* Checkbox */}
                  <label className="shrink-0">
                    <input
                      type="checkbox"
                      checked={selected.has(bundle.id)}
                      onChange={() => toggleSelect(bundle.id)}
                      disabled={!analysis || (!selected.has(bundle.id) && selected.size >= 2)}
                      className="w-4 h-4 rounded border-navy-600 bg-navy-700 text-[#8b5cf6] focus:ring-[#8b5cf6] focus:ring-offset-0 disabled:opacity-30"
                    />
                  </label>

                  {/* Health score mini */}
                  {analysis && (
                    <div className="shrink-0">
                      <HealthScore score={analysis.cluster_health.score} size={48} />
                    </div>
                  )}

                  {/* Bundle info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-200 truncate">{bundle.filename}</p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {(() => {
                        try { return format(new Date(bundle.upload_time), 'MMM d, yyyy HH:mm'); }
                        catch { return bundle.upload_time; }
                      })()}
                    </p>
                  </div>

                  {/* Issue counts */}
                  {analysis && (
                    <div className="flex items-center gap-3 shrink-0">
                      <span className="flex items-center gap-1 text-xs text-red-400">
                        <AlertCircle size={12} />
                        {analysis.cluster_health.critical_count}
                      </span>
                      <span className="flex items-center gap-1 text-xs text-amber-400">
                        <AlertTriangle size={12} />
                        {analysis.cluster_health.warning_count}
                      </span>
                      <span className="flex items-center gap-1 text-xs text-blue-400">
                        <Info size={12} />
                        {analysis.cluster_health.info_count}
                      </span>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex items-center gap-2 shrink-0">
                    {analysis && (
                      <button
                        onClick={() => navigate(`/analysis/${bundle.id}`)}
                        className="flex items-center gap-1 px-3 py-1.5 bg-[#06b6d4]/10 text-[#06b6d4] text-xs font-medium rounded-lg hover:bg-[#06b6d4]/20 transition-colors"
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
                  <div className="border-t border-navy-700 bg-navy-800/50 px-4 py-3">
                    <p className="text-xs font-medium text-gray-500 mb-2 uppercase tracking-wide">Analysis Runs</p>
                    <div className="space-y-1.5">
                      {history.map((entry, i) => (
                        <div
                          key={i}
                          className="flex items-center justify-between py-2 px-3 bg-navy-700/50 rounded-lg text-xs"
                        >
                          <div className="flex items-center gap-3">
                            <span className={clsx(
                              'font-bold text-sm',
                              entry.health_score > 70 ? 'text-[#06b6d4]' :
                              entry.health_score > 40 ? 'text-amber-400' : 'text-red-400'
                            )}>
                              {entry.health_score}%
                            </span>
                            <span className="text-gray-400">
                              {(() => {
                                try { return format(new Date(entry.analyzed_at), 'MMM d, yyyy HH:mm:ss'); }
                                catch { return entry.analyzed_at; }
                              })()}
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
