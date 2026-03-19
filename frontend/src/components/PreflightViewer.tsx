import { useState, useEffect } from 'react';
import { Shield, Copy, Download, X, CheckCircle, Loader2 } from 'lucide-react';
import { getPreflightSpec } from '../api/client';

interface PreflightViewerProps {
  bundleId: string;
  onClose: () => void;
}

function highlightYaml(yaml: string): JSX.Element[] {
  return yaml.split('\n').map((line, idx) => {
    const keyMatch = line.match(/^(\s*)([\w.-]+)(:)(.*)/);
    if (keyMatch) {
      const [, indent, key, colon, rest] = keyMatch;
      return (
        <span key={idx}>
          {indent}
          <span className="text-cyan-400">{key}</span>
          <span className="text-gray-400">{colon}</span>
          <span className="text-amber-300">{rest}</span>
          {'\n'}
        </span>
      );
    }

    const dashMatch = line.match(/^(\s*)(- )(.*)/);
    if (dashMatch) {
      const [, indent, dash, rest] = dashMatch;
      const innerKeyMatch = rest.match(/^([\w.-]+)(:)(.*)/);
      if (innerKeyMatch) {
        const [, iKey, iColon, iRest] = innerKeyMatch;
        return (
          <span key={idx}>
            {indent}
            <span className="text-gray-500">{dash}</span>
            <span className="text-cyan-400">{iKey}</span>
            <span className="text-gray-400">{iColon}</span>
            <span className="text-amber-300">{iRest}</span>
            {'\n'}
          </span>
        );
      }
      return (
        <span key={idx}>
          {indent}
          <span className="text-gray-500">{dash}</span>
          <span className="text-gray-300">{rest}</span>
          {'\n'}
        </span>
      );
    }

    if (line.trim().startsWith('#')) {
      return (
        <span key={idx} className="text-gray-600">
          {line}
          {'\n'}
        </span>
      );
    }

    return (
      <span key={idx} className="text-gray-300">
        {line}
        {'\n'}
      </span>
    );
  });
}

export default function PreflightViewer({ bundleId, onClose }: PreflightViewerProps) {
  const [yamlContent, setYamlContent] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function fetchSpec() {
      try {
        const spec = await getPreflightSpec(bundleId);
        if (!cancelled) {
          setYamlContent(spec);
        }
      } catch {
        if (!cancelled) {
          setError('Failed to generate preflight spec. Ensure the bundle has been analyzed.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    fetchSpec();
    return () => {
      cancelled = true;
    };
  }, [bundleId]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(yamlContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = yamlContent;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = () => {
    const blob = new Blob([yamlContent], { type: 'text/yaml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'preflight-spec.yaml';
    document.body.appendChild(a);
    a.click();
    URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose} role="dialog" aria-modal="true" aria-label="Generated preflight checks">
      <div
        className="bg-navy-800 border border-navy-600 rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-navy-600">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-emerald-500/20 rounded-lg flex items-center justify-center">
              <Shield size={18} className="text-emerald-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">Generated Preflight Checks</h2>
              <p className="text-xs text-gray-500">Troubleshoot.sh v1beta2 preflight spec &mdash; run with <code className="text-gray-400">kubectl preflight</code></p>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close preflight checks modal"
            className="w-8 h-8 rounded-lg hover:bg-navy-700 flex items-center justify-center text-gray-400 hover:text-white transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading && (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <Loader2 size={32} className="text-emerald-400 animate-spin" />
              <p className="text-sm text-gray-400">Generating preflight checks...</p>
            </div>
          )}
          {error && (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <Shield size={32} className="text-red-400" />
              <p className="text-sm text-red-400">{error}</p>
            </div>
          )}
          {!loading && !error && (
            <div className="bg-navy-900 border border-navy-700 rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 border-b border-navy-700 bg-navy-800/50">
                <span className="text-xs font-mono text-gray-500">preflight-spec.yaml</span>
                <span className="text-xs text-gray-600">{yamlContent.split('\n').length} lines</span>
              </div>
              <pre className="p-4 text-sm font-mono leading-relaxed overflow-x-auto max-h-[50vh] overflow-y-auto">
                <code>{highlightYaml(yamlContent)}</code>
              </pre>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-navy-600">
          <button
            onClick={handleCopy}
            disabled={loading || !!error}
            className="flex items-center gap-1.5 px-4 py-2 border border-navy-500 text-gray-300 text-sm font-medium rounded-lg hover:bg-navy-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {copied ? <CheckCircle size={14} className="text-green-400" /> : <Copy size={14} />}
            {copied ? 'Copied' : 'Copy YAML'}
          </button>
          <button
            onClick={handleDownload}
            disabled={loading || !!error}
            className="flex items-center gap-1.5 px-4 py-2 border border-navy-500 text-gray-300 text-sm font-medium rounded-lg hover:bg-navy-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Download size={14} />
            Download
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-navy-700 text-gray-300 text-sm font-medium rounded-lg hover:bg-navy-600 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
