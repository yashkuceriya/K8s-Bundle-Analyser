import { useState } from 'react';
import { ClipboardList, Copy, Download, X, CheckCircle } from 'lucide-react';
import { format } from 'date-fns';
import type { AnalysisResult } from '../types';

interface PlaybookExportProps {
  analysis: AnalysisResult;
  bundleFilename?: string;
}

function generatePlaybookMarkdown(analysis: AnalysisResult, bundleFilename?: string): string {
  const { cluster_health: health, issues } = analysis;

  const analyzedDate = (() => {
    try {
      return format(new Date(analysis.analyzed_at), 'MMMM d, yyyy HH:mm');
    } catch {
      return analysis.analyzed_at || 'Unknown';
    }
  })();

  const actionableIssues = issues
    .filter((i) => i.severity === 'critical' || i.severity === 'warning')
    .sort((a, b) => {
      const order: Record<string, number> = { critical: 0, warning: 1 };
      return (order[a.severity] ?? 2) - (order[b.severity] ?? 2);
    });

  let md = `# Remediation Playbook\n\n`;
  md += `## Summary\n\n`;
  md += `- **Bundle**: ${bundleFilename || analysis.bundle_id}\n`;
  md += `- **Analyzed**: ${analyzedDate}\n`;
  md += `- **Health Score**: ${health.score}/100\n`;
  md += `- **Issues**: ${health.critical_count} critical, ${health.warning_count} warnings\n\n`;

  md += `## Action Items\n\n`;

  if (actionableIssues.length === 0) {
    md += `No critical or warning issues detected. The cluster appears healthy.\n\n`;
  } else {
    actionableIssues.forEach((issue, idx) => {
      const severityIcon = issue.severity === 'critical' ? '\u{1F6A8}' : '\u{26A0}\u{FE0F}';
      const severityLabel = issue.severity === 'critical' ? 'Critical' : 'Warning';
      const resource = issue.resource ? `${issue.resource}` : 'N/A';
      const namespace = issue.namespace || 'default';

      md += `### ${severityIcon} ${issue.title}\n\n`;
      md += `**Severity**: ${severityLabel}\n`;
      md += `**Resource**: ${resource} (namespace: ${namespace})\n\n`;

      const explanation = issue.ai_explanation?.root_cause || issue.description;
      md += `**What's happening**: ${explanation}\n\n`;

      if (issue.proposed_fixes && issue.proposed_fixes.length > 0) {
        md += `**Steps to fix**:\n\n`;
        issue.proposed_fixes.forEach((fix, fixIdx) => {
          md += `${fixIdx + 1}. ${fix.description}\n`;
          if (fix.command) {
            md += `   \`\`\`\n   ${fix.command}\n   \`\`\`\n`;
          }
        });
        md += `\n`;
      } else if (issue.remediation) {
        md += `**How to fix**: ${issue.remediation}\n\n`;
      }

      if (idx < actionableIssues.length - 1) {
        md += `---\n\n`;
      }
    });
  }

  md += `## Verification Steps\n\n`;
  md += `After applying fixes, generate a new support bundle and re-analyze to verify resolution.\n`;

  return md;
}

export default function PlaybookExport({ analysis, bundleFilename }: PlaybookExportProps) {
  const { cluster_health: health, issues } = analysis;
  const actionableIssues = issues
    .filter((i) => i.severity === 'critical' || i.severity === 'warning')
    .sort((a, b) => {
      const order: Record<string, number> = { critical: 0, warning: 1 };
      return (order[a.severity] ?? 2) - (order[b.severity] ?? 2);
    });

  const analyzedDate = (() => {
    try {
      return format(new Date(analysis.analyzed_at), 'MMMM d, yyyy HH:mm');
    } catch {
      return analysis.analyzed_at || 'Unknown';
    }
  })();

  return (
    <div className="bg-navy-700 rounded-xl p-5 max-h-[70vh] overflow-y-auto font-mono text-sm leading-relaxed">
      {/* Summary Section */}
      <div className="mb-6">
        <h3 className="text-base font-bold text-white mb-3">Summary</h3>
        <div className="space-y-1 text-gray-300">
          <p><span className="text-gray-500">Bundle:</span> {bundleFilename || analysis.bundle_id}</p>
          <p><span className="text-gray-500">Analyzed:</span> {analyzedDate}</p>
          <p>
            <span className="text-gray-500">Health Score:</span>{' '}
            <span className={health.score >= 70 ? 'text-green-400' : health.score >= 40 ? 'text-amber-400' : 'text-red-400'}>
              {health.score}/100
            </span>
          </p>
          <p>
            <span className="text-gray-500">Issues:</span>{' '}
            {health.critical_count > 0 && <span className="text-red-400">{health.critical_count} critical</span>}
            {health.critical_count > 0 && health.warning_count > 0 && ', '}
            {health.warning_count > 0 && <span className="text-amber-400">{health.warning_count} warnings</span>}
            {health.critical_count === 0 && health.warning_count === 0 && <span className="text-green-400">None</span>}
          </p>
        </div>
      </div>

      {/* Action Items */}
      <div className="mb-6">
        <h3 className="text-base font-bold text-white mb-3">Action Items</h3>
        {actionableIssues.length === 0 ? (
          <p className="text-gray-400">No critical or warning issues detected. The cluster appears healthy.</p>
        ) : (
          <div className="space-y-4">
            {actionableIssues.map((issue, idx) => (
              <div key={issue.id || idx} className="bg-navy-800 border border-navy-600 rounded-lg p-4">
                <div className="flex items-start gap-2 mb-2">
                  <span className="text-base">{issue.severity === 'critical' ? '\u{1F6A8}' : '\u{26A0}\u{FE0F}'}</span>
                  <h4 className="text-sm font-semibold text-white">{issue.title}</h4>
                </div>
                <div className="space-y-1.5 text-xs text-gray-400 ml-7">
                  <p>
                    <span className="text-gray-500">Severity:</span>{' '}
                    <span className={issue.severity === 'critical' ? 'text-red-400' : 'text-amber-400'}>
                      {issue.severity === 'critical' ? 'Critical' : 'Warning'}
                    </span>
                  </p>
                  {issue.resource && (
                    <p>
                      <span className="text-gray-500">Resource:</span>{' '}
                      {issue.resource} (namespace: {issue.namespace || 'default'})
                    </p>
                  )}
                  <div className="mt-2">
                    <p className="text-gray-500 mb-1">What&apos;s happening:</p>
                    <p className="text-gray-300">{issue.ai_explanation?.root_cause || issue.description}</p>
                  </div>
                  {issue.proposed_fixes && issue.proposed_fixes.length > 0 && (
                    <div className="mt-2">
                      <p className="text-gray-500 mb-1">Steps to fix:</p>
                      <ol className="list-decimal list-inside space-y-1.5">
                        {issue.proposed_fixes.map((fix, fixIdx) => (
                          <li key={fix.id || fixIdx} className="text-gray-300">
                            {fix.description}
                            {fix.command && (
                              <pre className="mt-1 ml-4 bg-navy-900 rounded p-2 text-xs text-gray-300 overflow-x-auto">
                                {fix.command}
                              </pre>
                            )}
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}
                  {(!issue.proposed_fixes || issue.proposed_fixes.length === 0) && issue.remediation && (
                    <div className="mt-2">
                      <p className="text-gray-500 mb-1">How to fix:</p>
                      <p className="text-gray-300">{issue.remediation}</p>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Verification */}
      <div>
        <h3 className="text-base font-bold text-white mb-2">Verification Steps</h3>
        <p className="text-gray-400 text-xs">
          After applying fixes, generate a new support bundle and re-analyze to verify resolution.
        </p>
      </div>
    </div>
  );
}

export function PlaybookModal({
  analysis,
  bundleFilename,
  onClose,
}: PlaybookExportProps & { onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const markdown = generatePlaybookMarkdown(analysis, bundleFilename);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = markdown;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = () => {
    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `playbook-${analysis.bundle_id}.md`;
    document.body.appendChild(a);
    a.click();
    URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose} role="dialog" aria-modal="true" aria-label="Remediation playbook">
      <div
        className="bg-navy-800 border border-navy-600 rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-navy-600">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-accent-purple/20 rounded-lg flex items-center justify-center">
              <ClipboardList size={18} className="text-accent-purple" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">Remediation Playbook</h2>
              <p className="text-xs text-gray-500">Share this with the cluster operator to resolve detected issues</p>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close playbook modal"
            className="w-8 h-8 rounded-lg hover:bg-navy-700 flex items-center justify-center text-gray-400 hover:text-white transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Content */}
        <div className="flex-1 overflow-y-auto p-6">
          <PlaybookExport analysis={analysis} bundleFilename={bundleFilename} />
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-navy-600">
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 px-4 py-2 border border-navy-500 text-gray-300 text-sm font-medium rounded-lg hover:bg-navy-700 transition-colors"
          >
            {copied ? <CheckCircle size={14} className="text-green-400" /> : <Copy size={14} />}
            {copied ? 'Copied' : 'Copy to Clipboard'}
          </button>
          <button
            onClick={handleDownload}
            className="flex items-center gap-1.5 px-4 py-2 border border-navy-500 text-gray-300 text-sm font-medium rounded-lg hover:bg-navy-700 transition-colors"
          >
            <Download size={14} />
            Download as Markdown
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
