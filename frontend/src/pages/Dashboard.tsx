import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  Upload,
  FileArchive,
  Trash2,
  CheckCircle,
  AlertCircle,
  Clock,
  Zap,
  ArrowRight,
  Plus,
} from 'lucide-react';
import { format } from 'date-fns';
import clsx from 'clsx';
import Navbar from '../components/Navbar';
import LoadingSpinner from '../components/LoadingSpinner';
import HealthScore from '../components/HealthScore';
import { uploadBundle, getBundles, analyzeBundle, deleteBundle } from '../api/client';
import type { BundleInfo } from '../types';

const statusConfig: Record<string, { icon: React.ReactNode; color: string; bg: string; dot: string }> = {
  uploaded: {
    icon: <Clock size={14} />,
    color: 'text-gray-400',
    bg: 'bg-gray-500/20',
    dot: 'bg-gray-400',
  },
  analyzing: {
    icon: <Clock size={14} className="animate-spin" />,
    color: 'text-[#06b6d4]',
    bg: 'bg-cyan-500/20',
    dot: 'bg-cyan-400 animate-pulse',
  },
  completed: {
    icon: <CheckCircle size={14} />,
    color: 'text-emerald-400',
    bg: 'bg-emerald-500/20',
    dot: 'bg-emerald-400',
  },
  failed: {
    icon: <AlertCircle size={14} />,
    color: 'text-red-400',
    bg: 'bg-red-500/20',
    dot: 'bg-red-400',
  },
};

export default function Dashboard() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [bundles, setBundles] = useState<BundleInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadedBundle, setUploadedBundle] = useState<BundleInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const hasLoadedOnce = useRef(false);
  const fetchBundles = useCallback(async () => {
    try {
      const data = await getBundles();
      setBundles(data);
      setError(null);
      hasLoadedOnce.current = true;
    } catch {
      // Only show the error banner after the first successful load,
      // so the initial page render doesn't flash "Failed to load bundles"
      // when the backend is still starting up.
      if (hasLoadedOnce.current) {
        setError('Failed to load bundles.');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBundles();
  }, [fetchBundles]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      const bundle = await uploadBundle(file);
      setUploadedBundle(bundle);
      await fetchBundles();
      // Auto-trigger analysis
      setUploading(false);
      setAnalyzing(bundle.id);
      try {
        await analyzeBundle(bundle.id);
        setUploadedBundle(null);
        navigate(`/analysis/${bundle.id}`);
      } catch {
        setError('Analysis failed. Please try again.');
        await fetchBundles();
      } finally {
        setAnalyzing(null);
      }
    } catch {
      setError('Failed to upload bundle. Please try again.');
      setUploading(false);
    }
  };

  const handleAnalyze = async (bundleId: string) => {
    setAnalyzing(bundleId);
    setError(null);
    try {
      await analyzeBundle(bundleId);
      setUploadedBundle(null);
      navigate(`/analysis/${bundleId}`);
    } catch {
      setError('Analysis failed. Please try again.');
      await fetchBundles();
    } finally {
      setAnalyzing(null);
    }
  };

  const handleDelete = async (bundleId: string) => {
    try {
      await deleteBundle(bundleId);
      if (uploadedBundle?.id === bundleId) setUploadedBundle(null);
      await fetchBundles();
    } catch {
      setError('Failed to delete bundle.');
    }
  };

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleUpload(file);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
  };

  return (
    <div className="min-h-screen bg-navy-900">
      <Navbar />
      <main className="px-8 py-8 max-w-screen-2xl mx-auto space-y-8">

        {/* Top 2-column section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Hero */}
          <div className="space-y-4">
            <h1 className="text-5xl font-bold text-white leading-[1.1]">
              Support Bundle<br />Intelligence
            </h1>
            <p className="text-sm text-gray-400 leading-relaxed max-w-sm">
              Automated Kubernetes diagnostics. Upload a troubleshoot.sh support bundle for instant root cause analysis, health scoring, and remediation playbooks.
            </p>
            <div className="flex items-center gap-8 pt-4">
              <div>
                <p className="text-3xl font-bold text-white">{bundles.length}</p>
                <p className="text-[10px] text-gray-500 uppercase tracking-widest font-semibold">Bundles</p>
              </div>
              <div>
                <p className="text-3xl font-bold text-red-400">
                  {bundles.reduce((sum, b) => sum + (b.analysis?.issues?.filter((i: any) => i.severity === 'critical').length ?? 0), 0)}
                </p>
                <p className="text-[10px] text-gray-500 uppercase tracking-widest font-semibold">Critical Issues</p>
              </div>
              <div>
                <p className="text-3xl font-bold text-emerald-400">
                  {bundles.filter(b => b.status === 'completed').length}
                </p>
                <p className="text-[10px] text-gray-500 uppercase tracking-widest font-semibold">Analyzed</p>
              </div>
            </div>
          </div>

          {/* Upload Zone */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            className={clsx(
              'border-2 border-dashed rounded-2xl p-8 flex flex-col items-center justify-center gap-4 cursor-pointer transition-all',
              dragOver
                ? 'border-accent-blue bg-accent-blue/5'
                : 'border-navy-600 hover:border-navy-500 bg-navy-800/30'
            )}
          >
            <input
              ref={fileInputRef}
              type="file"
              onChange={onFileChange}
              accept=".tar.gz,.tgz,.gz,application/gzip,application/x-gzip,application/x-compressed-tar"
              aria-label="Upload support bundle file"
              className="hidden"
            />
            {(uploading || analyzing) ? (
              <LoadingSpinner size={32} label={analyzing ? "Analyzing bundle..." : "Uploading..."} />
            ) : (
              <>
                <div className="w-14 h-14 bg-navy-700 rounded-2xl flex items-center justify-center border border-navy-600">
                  <Upload size={24} className="text-accent-blue" />
                </div>
                <div className="text-center">
                  <p className="text-sm text-gray-300 font-medium">
                    Drag and drop <span className="text-accent-blue">.tar.gz</span> bundle
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    Supports Kubernetes diagnostic bundles,<br />log exports, and Prometheus snapshots up to 500MB.
                  </p>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
                  className="px-5 py-2 bg-accent-blue hover:bg-blue-600 text-white text-sm font-semibold rounded-xl transition-colors shadow-lg shadow-blue-500/20"
                >
                  Select Bundle
                </button>
              </>
            )}
          </div>

        </div>

        {/* Uploaded bundle action bar */}
        {uploadedBundle && !analyzing && (
          <div className="flex items-center justify-between bg-navy-800 border border-accent-blue/30 rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-accent-blue/10 rounded-lg flex items-center justify-center">
                <FileArchive size={20} className="text-accent-blue" />
              </div>
              <div>
                <span className="text-sm text-gray-200 font-medium">{uploadedBundle.filename}</span>
                <p className="text-xs text-gray-500">Ready for analysis</p>
              </div>
            </div>
            <button
              onClick={() => handleAnalyze(uploadedBundle.id)}
              className="flex items-center gap-2 px-5 py-2.5 bg-accent-blue hover:bg-blue-600 text-white text-sm font-semibold rounded-xl transition-all duration-200 shadow-lg shadow-blue-500/20"
            >
              <Zap size={16} />
              Analyze Bundle
            </button>
          </div>
        )}

        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-center gap-3">
            <AlertCircle size={18} className="text-red-400 shrink-0" />
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {/* Currently Analyzing */}
        {analyzing && (
          <div className="bg-navy-800 border border-navy-700 rounded-xl p-5">
            <div className="flex items-center gap-3 mb-3">
              <span className="w-2 h-2 rounded-full bg-accent-blue animate-pulse" />
              <span className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Currently Analyzing</span>
            </div>
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 bg-navy-700 rounded-xl flex items-center justify-center">
                <div className="w-6 h-6 border-2 border-accent-blue border-t-transparent rounded-full animate-spin" />
              </div>
              <div className="flex-1 space-y-2">
                <div className="h-3 bg-navy-700 rounded-full w-3/4 animate-pulse" />
                <div className="h-2 bg-navy-700 rounded-full w-1/2 animate-pulse" />
              </div>
            </div>
          </div>
        )}

        {/* Recent History */}
        <section>
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-xl font-bold text-white">Recent History</h2>
            {bundles.length > 0 && (
              <Link
                to="/history"
                className="text-xs text-accent-blue hover:text-blue-400 font-medium transition-colors"
              >
                View All →
              </Link>
            )}
          </div>
          {loading ? (
            <LoadingSpinner size={32} label="Loading bundles..." className="py-12" />
          ) : bundles.length === 0 ? (
            <div className="bg-navy-800/50 border border-navy-700 rounded-xl p-12 text-center">
              <FileArchive size={36} className="text-gray-700 mx-auto mb-3" />
              <p className="text-gray-500 text-sm">No bundles uploaded yet</p>
              <p className="text-xs text-gray-600 mt-1">Upload a support bundle above to get started</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {bundles.map((bundle) => {
                const cfg = statusConfig[bundle.status] || statusConfig.uploaded;
                const analysis = bundle.analysis;
                const criticalCount = analysis?.issues?.filter((i) => i.severity === 'critical' || i.severity === 'error').length ?? 0;
                const warningCount = analysis?.issues?.filter((i) => i.severity === 'warning').length ?? 0;
                const infoCount = analysis?.issues?.filter((i) => i.severity === 'info').length ?? 0;
                const healthScore = analysis?.health_score ?? null;

                return (
                  <div
                    key={bundle.id}
                    onClick={() => bundle.status === 'completed' ? navigate(`/analysis/${bundle.id}`) : undefined}
                    className={clsx(
                      'bg-navy-800 border border-navy-700 rounded-xl p-5 transition-all hover:border-navy-600 group',
                      bundle.status === 'completed' && 'cursor-pointer hover:shadow-lg hover:shadow-navy-900/50'
                    )}
                  >
                    {/* Header */}
                    <div className="flex items-center justify-between mb-4">
                      <div className="min-w-0 flex-1 mr-3">
                        <p className="text-sm font-semibold text-gray-200 truncate">{bundle.filename}</p>
                        <p className="text-xs text-gray-500 mt-0.5">
                          {(() => {
                            try { return `Uploaded ${format(new Date(bundle.upload_time), 'MMM d, HH:mm')}`; }
                            catch { return bundle.upload_time; }
                          })()}
                        </p>
                      </div>
                      <span className={clsx(
                        'px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider shrink-0',
                        cfg.bg, cfg.color
                      )}>
                        {bundle.status}
                      </span>
                    </div>

                    {/* Progress bar for analyzing bundles */}
                    {bundle.status === 'analyzing' && (
                      <div className="mb-4">
                        <div className="w-full h-1.5 bg-navy-700 rounded-full overflow-hidden">
                          <div className="h-full bg-accent-blue rounded-full animate-pulse" style={{ width: '60%' }} />
                        </div>
                      </div>
                    )}

                    {/* Score + Stats */}
                    <div className="flex items-center justify-between">
                      <div className="shrink-0">
                        {healthScore !== null ? (
                          <HealthScore score={healthScore} size={72} />
                        ) : (
                          <div className="w-[72px] h-[72px] rounded-full border-[6px] border-navy-700 flex items-center justify-center bg-navy-900/50">
                            <span className="text-lg font-bold text-gray-600">--</span>
                          </div>
                        )}
                      </div>
                      <div className="flex gap-4 text-xs">
                        <div className="text-center">
                          <p className="text-red-400 font-semibold">{bundle.status === 'completed' ? criticalCount : '--'}</p>
                          <p className="text-gray-500 text-[10px]">Critical</p>
                        </div>
                        <div className="text-center">
                          <p className="text-amber-400 font-semibold">{bundle.status === 'completed' ? warningCount : '--'}</p>
                          <p className="text-gray-500 text-[10px]">Warnings</p>
                        </div>
                        <div className="text-center">
                          <p className="text-accent-blue font-semibold">{bundle.status === 'completed' ? infoCount : '--'}</p>
                          <p className="text-gray-500 text-[10px]">Info</p>
                        </div>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center justify-between mt-4 pt-3 border-t border-navy-700">
                      {bundle.status === 'uploaded' && (
                        <button
                          onClick={(e) => { e.stopPropagation(); handleAnalyze(bundle.id); }}
                          disabled={analyzing === bundle.id}
                          className="text-xs text-accent-blue hover:text-blue-400 font-medium disabled:opacity-50"
                        >
                          {analyzing === bundle.id ? 'Analyzing...' : 'Analyze'}
                        </button>
                      )}
                      {bundle.status === 'completed' && (
                        <span className="text-xs text-accent-blue font-medium flex items-center gap-1">
                          View Results <ArrowRight size={12} />
                        </span>
                      )}
                      {bundle.status === 'analyzing' && (
                        <span className="text-xs text-gray-500 font-medium">Processing...</span>
                      )}
                      {bundle.status === 'failed' && (
                        <span className="text-xs text-red-400 font-medium">Failed</span>
                      )}
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDelete(bundle.id); }}
                        className="p-1.5 text-gray-600 hover:text-red-400 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                        aria-label="Delete bundle"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                );
              })}

              {/* Upload New Card */}
              <div
                onClick={() => fileInputRef.current?.click()}
                className="bg-navy-800/30 border-2 border-dashed border-navy-700 rounded-xl p-5 flex flex-col items-center justify-center gap-3 cursor-pointer hover:border-navy-600 hover:bg-navy-800/50 transition-all min-h-[200px]"
              >
                <div className="w-12 h-12 bg-navy-700 rounded-xl flex items-center justify-center border border-navy-600">
                  <Plus size={24} className="text-gray-500" />
                </div>
                <p className="text-sm text-gray-400 font-medium">Upload New Cluster Data</p>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
