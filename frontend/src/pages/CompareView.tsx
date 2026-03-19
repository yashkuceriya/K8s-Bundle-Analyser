import { useState, useEffect, useMemo } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { GitCompare, ArrowLeft, Download, AlertCircle, AlertTriangle, Info, CheckCircle, MinusCircle } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import clsx from 'clsx';
import Navbar from '../components/Navbar';
import HealthScore from '../components/HealthScore';
import LoadingSpinner from '../components/LoadingSpinner';
import SeverityBadge from '../components/SeverityBadge';
import { compareAnalyses, getBundle } from '../api/client';
import type { AnalysisResult, BundleInfo, Issue } from '../types';

interface IssueDiff {
  title: string;
  side: 'left' | 'right' | 'both';
  leftIssue?: Issue;
  rightIssue?: Issue;
}

export default function CompareView() {
  const [params] = useSearchParams();
  const leftId = params.get('left') || '';
  const rightId = params.get('right') || '';

  const [leftAnalysis, setLeftAnalysis] = useState<AnalysisResult | null>(null);
  const [rightAnalysis, setRightAnalysis] = useState<AnalysisResult | null>(null);
  const [leftBundle, setLeftBundle] = useState<BundleInfo | null>(null);
  const [rightBundle, setRightBundle] = useState<BundleInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!leftId || !rightId) {
      setError('Missing bundle IDs for comparison');
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const [comparison, lb, rb] = await Promise.all([
          compareAnalyses({ left_bundle_id: leftId, right_bundle_id: rightId }),
          getBundle(leftId),
          getBundle(rightId),
        ]);
        setLeftAnalysis(comparison.left);
        setRightAnalysis(comparison.right);
        setLeftBundle(lb);
        setRightBundle(rb);
      } catch {
        setError('Failed to load comparison data');
      } finally {
        setLoading(false);
      }
    })();
  }, [leftId, rightId]);

  const severityChartData = useMemo(() => {
    if (!leftAnalysis || !rightAnalysis) return [];
    return [
      { name: 'Critical', left: leftAnalysis.cluster_health.critical_count, right: rightAnalysis.cluster_health.critical_count },
      { name: 'Warning', left: leftAnalysis.cluster_health.warning_count, right: rightAnalysis.cluster_health.warning_count },
      { name: 'Info', left: leftAnalysis.cluster_health.info_count, right: rightAnalysis.cluster_health.info_count },
    ];
  }, [leftAnalysis, rightAnalysis]);

  const categoryChartData = useMemo(() => {
    if (!leftAnalysis || !rightAnalysis) return [];
    const cats = new Set<string>();
    leftAnalysis.issues.forEach(i => cats.add(i.category));
    rightAnalysis.issues.forEach(i => cats.add(i.category));
    return Array.from(cats).map(cat => ({
      name: cat,
      left: leftAnalysis.issues.filter(i => i.category === cat).length,
      right: rightAnalysis.issues.filter(i => i.category === cat).length,
    }));
  }, [leftAnalysis, rightAnalysis]);

  const issueDiff = useMemo<IssueDiff[]>(() => {
    if (!leftAnalysis || !rightAnalysis) return [];
    const leftMap = new Map(leftAnalysis.issues.map(i => [i.title, i]));
    const rightMap = new Map(rightAnalysis.issues.map(i => [i.title, i]));
    const allTitles = new Set([...leftMap.keys(), ...rightMap.keys()]);
    const diffs: IssueDiff[] = [];
    for (const title of allTitles) {
      const l = leftMap.get(title);
      const r = rightMap.get(title);
      diffs.push({
        title,
        side: l && r ? 'both' : l ? 'left' : 'right',
        leftIssue: l,
        rightIssue: r,
      });
    }
    // Sort: both first, then left-only, then right-only
    diffs.sort((a, b) => {
      const order = { both: 0, left: 1, right: 2 };
      return order[a.side] - order[b.side];
    });
    return diffs;
  }, [leftAnalysis, rightAnalysis]);

  const handleExport = () => {
    if (!leftAnalysis || !rightAnalysis) return;
    const report = {
      generated_at: new Date().toISOString(),
      left: { bundle_id: leftId, filename: leftBundle?.filename, analysis: leftAnalysis },
      right: { bundle_id: rightId, filename: rightBundle?.filename, analysis: rightAnalysis },
      issue_diff: issueDiff.map(d => ({ title: d.title, side: d.side })),
    };
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `comparison-${leftId.slice(0, 8)}-${rightId.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-navy-900">
        <Navbar />
        <LoadingSpinner size={40} label="Loading comparison..." className="py-24" />
      </div>
    );
  }

  if (error || !leftAnalysis || !rightAnalysis) {
    return (
      <div className="min-h-screen bg-navy-900">
        <Navbar />
        <div className="max-w-screen-lg mx-auto px-6 py-16 text-center">
          <AlertCircle size={40} className="text-red-400 mx-auto mb-4" />
          <p className="text-red-400">{error || 'Failed to load comparison'}</p>
          <Link to="/history" className="text-[#06b6d4] text-sm mt-4 inline-block hover:underline">Back to History</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-navy-900">
      <Navbar />
      <main className="max-w-screen-xl mx-auto px-6 py-10 space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/history" className="p-2 text-gray-500 hover:text-gray-300 hover:bg-navy-700 rounded-lg transition-colors">
              <ArrowLeft size={18} />
            </Link>
            <div className="w-10 h-10 bg-[#8b5cf6]/10 rounded-xl flex items-center justify-center">
              <GitCompare size={20} className="text-[#8b5cf6]" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">Analysis Comparison</h1>
              <p className="text-xs text-gray-500">Side-by-side analysis results</p>
            </div>
          </div>
          <button
            onClick={handleExport}
            className="flex items-center gap-2 px-4 py-2 border border-navy-600 text-gray-300 text-sm font-medium rounded-xl hover:bg-navy-700 transition-colors"
          >
            <Download size={14} />
            Export Report
          </button>
        </div>

        {/* Health Score Comparison */}
        <div className="grid grid-cols-2 gap-6">
          {[
            { label: 'Left', analysis: leftAnalysis, bundle: leftBundle },
            { label: 'Right', analysis: rightAnalysis, bundle: rightBundle },
          ].map(({ label, analysis, bundle }) => (
            <div key={label} className="bg-navy-800 border border-navy-700 rounded-xl p-6 flex flex-col items-center gap-3">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label} Bundle</p>
              <p className="text-sm font-medium text-gray-300 truncate max-w-full">{bundle?.filename || 'Unknown'}</p>
              <HealthScore score={analysis.cluster_health.score} size={120} />
              <div className="flex items-center gap-4 mt-2">
                <span className="flex items-center gap-1 text-xs text-red-400">
                  <AlertCircle size={12} /> {analysis.cluster_health.critical_count} critical
                </span>
                <span className="flex items-center gap-1 text-xs text-amber-400">
                  <AlertTriangle size={12} /> {analysis.cluster_health.warning_count} warning
                </span>
                <span className="flex items-center gap-1 text-xs text-blue-400">
                  <Info size={12} /> {analysis.cluster_health.info_count} info
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Charts */}
        <div className="grid grid-cols-2 gap-6">
          {/* Severity chart */}
          <div className="bg-navy-800 border border-navy-700 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-white mb-4">Issues by Severity</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={severityChartData} barGap={4}>
                <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#6b7280', fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1a2332', border: '1px solid #2d3748', borderRadius: '8px' }}
                  labelStyle={{ color: '#e5e7eb' }}
                  itemStyle={{ color: '#e5e7eb' }}
                />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Bar dataKey="left" name={leftBundle?.filename?.slice(0, 20) || 'Left'} fill="#06b6d4" radius={[4, 4, 0, 0]} />
                <Bar dataKey="right" name={rightBundle?.filename?.slice(0, 20) || 'Right'} fill="#8b5cf6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Category chart */}
          <div className="bg-navy-800 border border-navy-700 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-white mb-4">Issues by Category</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={categoryChartData} barGap={4}>
                <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#6b7280', fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1a2332', border: '1px solid #2d3748', borderRadius: '8px' }}
                  labelStyle={{ color: '#e5e7eb' }}
                  itemStyle={{ color: '#e5e7eb' }}
                />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Bar dataKey="left" name={leftBundle?.filename?.slice(0, 20) || 'Left'} fill="#06b6d4" radius={[4, 4, 0, 0]} />
                <Bar dataKey="right" name={rightBundle?.filename?.slice(0, 20) || 'Right'} fill="#8b5cf6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Issue Diff */}
        <div className="bg-navy-800 border border-navy-700 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-white mb-4">Issue Comparison</h3>
          <div className="flex items-center gap-4 mb-4 text-xs">
            <span className="flex items-center gap-1.5 text-gray-400">
              <CheckCircle size={12} className="text-emerald-400" /> In both
            </span>
            <span className="flex items-center gap-1.5 text-gray-400">
              <MinusCircle size={12} className="text-[#06b6d4]" /> Left only
            </span>
            <span className="flex items-center gap-1.5 text-gray-400">
              <MinusCircle size={12} className="text-[#8b5cf6]" /> Right only
            </span>
          </div>
          <div className="space-y-1.5">
            {issueDiff.map((diff, i) => {
              const issue = diff.leftIssue || diff.rightIssue;
              return (
                <div
                  key={i}
                  className={clsx(
                    'flex items-center gap-3 py-2.5 px-3 rounded-lg text-sm',
                    diff.side === 'both' ? 'bg-navy-700/30' :
                    diff.side === 'left' ? 'bg-[#06b6d4]/5 border border-[#06b6d4]/20' :
                    'bg-[#8b5cf6]/5 border border-[#8b5cf6]/20'
                  )}
                >
                  {diff.side === 'both' ? (
                    <CheckCircle size={14} className="text-emerald-400 shrink-0" />
                  ) : diff.side === 'left' ? (
                    <MinusCircle size={14} className="text-[#06b6d4] shrink-0" />
                  ) : (
                    <MinusCircle size={14} className="text-[#8b5cf6] shrink-0" />
                  )}
                  {issue && <SeverityBadge severity={issue.severity} />}
                  <span className="text-gray-300 truncate">{diff.title}</span>
                  <span className="text-xs text-gray-500 ml-auto shrink-0">
                    {diff.side === 'both' ? 'Both' : diff.side === 'left' ? 'Left only' : 'Right only'}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </main>
    </div>
  );
}
