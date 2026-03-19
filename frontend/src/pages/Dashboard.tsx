import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  Upload,
  FileArchive,
  Trash2,
  CheckCircle,
  AlertCircle,
  Clock,
  Shield,
  Zap,
  ArrowRight,
} from 'lucide-react';
import { format } from 'date-fns';
import clsx from 'clsx';
import Navbar from '../components/Navbar';
import LoadingSpinner from '../components/LoadingSpinner';
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

  const fetchBundles = useCallback(async () => {
    try {
      const data = await getBundles();
      setBundles(data);
    } catch {
      setError('Failed to load bundles.');
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
    } catch {
      setError('Failed to upload bundle. Please try again.');
    } finally {
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
      <main className="max-w-screen-lg mx-auto px-6 py-12 space-y-10">

        {/* Hero Section */}
        <div className="text-center space-y-4 py-4">
          <div className="flex items-center justify-center gap-3 mb-2">
            <div className="w-12 h-12 bg-gradient-to-br from-[#06b6d4]/20 to-[#8b5cf6]/20 rounded-2xl flex items-center justify-center border border-navy-600">
              <Shield size={24} className="text-[#06b6d4]" />
            </div>
          </div>
          <h1 className="text-3xl font-bold text-white tracking-tight">
            K8s Bundle Analyzer
          </h1>
          <p className="text-gray-400 max-w-lg mx-auto text-sm leading-relaxed">
            Automated Kubernetes troubleshooting for{' '}
            <span className="text-[#06b6d4]">Troubleshoot.sh</span> support bundles.
            Upload a bundle to run AI-powered root-cause analysis in seconds.
          </p>
        </div>

        {/* Upload Zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          className={clsx(
            'relative border-2 border-dashed rounded-2xl p-14 text-center cursor-pointer transition-all duration-300',
            dragOver
              ? 'border-[#06b6d4] bg-[#06b6d4]/5 shadow-[0_0_40px_rgba(6,182,212,0.15)]'
              : 'border-navy-600 hover:border-navy-500 bg-navy-800/30 hover:bg-navy-800/50 hover:shadow-[0_0_30px_rgba(6,182,212,0.06)]'
          )}
        >
          <input
            ref={fileInputRef}
            type="file"
            onChange={onFileChange}
            accept=".tar.gz,.tgz"
            aria-label="Upload support bundle file"
            className="hidden"
          />
          {uploading ? (
            <LoadingSpinner size={40} label="Uploading bundle..." />
          ) : analyzing ? (
            <LoadingSpinner size={40} label="Analyzing bundle..." />
          ) : (
            <div className="flex flex-col items-center gap-4">
              <div className="w-20 h-20 bg-navy-700/50 rounded-2xl flex items-center justify-center border border-navy-600">
                <Upload size={32} className="text-[#06b6d4]" />
              </div>
              <div>
                <p className="text-lg font-medium text-gray-200">
                  Drag and drop your <span className="text-[#06b6d4]">.tar.gz</span> support bundle
                </p>
                <p className="text-sm text-gray-500 mt-1">
                  Your bundle will be analyzed using our AI-powered engine to detect
                  pod failures, node pressures, and network issues.
                </p>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
                className="mt-2 px-6 py-2.5 bg-[#06b6d4] hover:bg-cyan-600 text-white text-sm font-semibold rounded-xl transition-all duration-200 shadow-lg shadow-cyan-500/20"
              >
                Browse Files
              </button>
            </div>
          )}
        </div>

        {/* Uploaded bundle action bar */}
        {uploadedBundle && !analyzing && (
          <div className="flex items-center justify-between bg-navy-800 border border-navy-600 rounded-xl p-4 shadow-lg">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-[#06b6d4]/10 rounded-lg flex items-center justify-center">
                <FileArchive size={20} className="text-[#06b6d4]" />
              </div>
              <div>
                <span className="text-sm text-gray-200 font-medium">{uploadedBundle.filename}</span>
                <p className="text-xs text-gray-500">Ready for analysis</p>
              </div>
            </div>
            <button
              onClick={() => handleAnalyze(uploadedBundle.id)}
              className="flex items-center gap-2 px-5 py-2.5 bg-[#06b6d4] hover:bg-cyan-600 text-white text-sm font-semibold rounded-xl transition-all duration-200 shadow-lg shadow-cyan-500/20"
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

        {/* Feature highlights */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[
            {
              icon: <Zap size={18} className="text-[#06b6d4]" />,
              title: 'Heuristic Detection',
              desc: '15+ pattern detectors for common K8s failures',
            },
            {
              icon: <Shield size={18} className="text-[#8b5cf6]" />,
              title: 'AI Root-Cause Analysis',
              desc: 'Correlates symptoms into causal chains',
            },
            {
              icon: <FileArchive size={18} className="text-[#10b981]" />,
              title: 'Actionable Output',
              desc: 'Playbooks, preflight checks, and reports',
            },
          ].map((f) => (
            <div key={f.title} className="bg-navy-800/50 border border-navy-700 rounded-xl p-4 flex items-start gap-3">
              <div className="w-9 h-9 bg-navy-700 rounded-lg flex items-center justify-center shrink-0">
                {f.icon}
              </div>
              <div>
                <p className="text-sm font-medium text-gray-200">{f.title}</p>
                <p className="text-xs text-gray-500 mt-0.5">{f.desc}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Recent Analysis */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-white">Recent Analysis</h2>
            {bundles.length > 0 && (
              <span className="text-xs text-gray-500">{bundles.length} bundle{bundles.length !== 1 ? 's' : ''}</span>
            )}
            <Link
              to="/history"
              className="text-xs text-[#8b5cf6] hover:text-violet-400 font-medium transition-colors"
            >
              View History →
            </Link>
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
            <div className="space-y-2">
              {bundles.map((bundle) => {
                const cfg = statusConfig[bundle.status] || statusConfig.uploaded;
                return (
                  <div
                    key={bundle.id}
                    className="bg-navy-800 border border-navy-700 rounded-xl p-4 flex items-center justify-between hover:border-navy-600 transition-colors group"
                  >
                    <div className="flex items-center gap-4 min-w-0">
                      <div className="w-10 h-10 bg-navy-700 rounded-lg flex items-center justify-center shrink-0">
                        <FileArchive size={18} className="text-gray-500" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-200 truncate">{bundle.filename}</p>
                        <p className="text-xs text-gray-500 mt-0.5">
                          {(() => {
                            try { return format(new Date(bundle.upload_time), 'MMM d, yyyy HH:mm'); }
                            catch { return bundle.upload_time; }
                          })()}
                        </p>
                      </div>
                      <span className={clsx('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium shrink-0', cfg.bg, cfg.color)}>
                        <span className={clsx('w-1.5 h-1.5 rounded-full', cfg.dot)} />
                        {bundle.status.charAt(0).toUpperCase() + bundle.status.slice(1)}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {bundle.status === 'completed' && (
                        <button
                          onClick={() => navigate(`/analysis/${bundle.id}`)}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-[#06b6d4]/10 text-[#06b6d4] text-xs font-medium rounded-lg hover:bg-[#06b6d4]/20 transition-colors"
                        >
                          View Results
                          <ArrowRight size={12} />
                        </button>
                      )}
                      {bundle.status === 'uploaded' && (
                        <button
                          onClick={() => handleAnalyze(bundle.id)}
                          disabled={analyzing === bundle.id}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-[#06b6d4]/10 text-[#06b6d4] text-xs font-medium rounded-lg hover:bg-[#06b6d4]/20 transition-colors disabled:opacity-50"
                        >
                          {analyzing === bundle.id ? <LoadingSpinner size={14} /> : 'Analyze'}
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(bundle.id)}
                        className="p-1.5 text-gray-600 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                        aria-label="Delete bundle"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-navy-800 py-4 text-center">
        <p className="text-xs text-gray-600">
          K8s Bundle Analyzer v1.0 &middot; Built for{' '}
          <a href="https://troubleshoot.sh" target="_blank" rel="noopener noreferrer" className="text-gray-500 hover:text-gray-400 transition-colors">
            Troubleshoot.sh
          </a>{' '}
          bundles &middot; 15 heuristic detectors + Claude AI
        </p>
      </footer>
    </div>
  );
}
