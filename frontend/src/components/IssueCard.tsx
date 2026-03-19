import { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Tag,
  Box,
  Brain,
  CheckCircle,
  Terminal,
  Copy,
  Wrench,
  AlertCircle,
  AlertTriangle,
  Info,
} from 'lucide-react';
import clsx from 'clsx';
import type { Issue } from '../types';

interface IssueCardProps {
  issue: Issue;
}

const severityConfig: Record<string, { border: string; iconColor: string; bgTint: string }> = {
  critical: { border: 'border-l-[#ef4444]', iconColor: 'text-[#ef4444]', bgTint: 'bg-red-500/5' },
  warning: { border: 'border-l-[#f59e0b]', iconColor: 'text-[#f59e0b]', bgTint: 'bg-amber-500/5' },
  info: { border: 'border-l-[#06b6d4]', iconColor: 'text-[#06b6d4]', bgTint: 'bg-cyan-500/5' },
};

function SeverityIcon({ severity, size = 28 }: { severity: string; size?: number }) {
  const cfg = severityConfig[severity] ?? severityConfig.info;
  if (severity === 'critical') {
    return (
      <div className={clsx('flex items-center justify-center shrink-0 rounded-full bg-red-500/15')} style={{ width: size + 12, height: size + 12 }}>
        <AlertCircle size={size} className={cfg.iconColor} />
      </div>
    );
  }
  if (severity === 'warning') {
    return (
      <div className={clsx('flex items-center justify-center shrink-0 rounded-full bg-amber-500/15')} style={{ width: size + 12, height: size + 12 }}>
        <AlertTriangle size={size} className={cfg.iconColor} />
      </div>
    );
  }
  return (
    <div className={clsx('flex items-center justify-center shrink-0 rounded-full bg-cyan-500/15')} style={{ width: size + 12, height: size + 12 }}>
      <Info size={size} className={cfg.iconColor} />
    </div>
  );
}

export default function IssueCard({ issue }: IssueCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [copiedCommand, setCopiedCommand] = useState<string | null>(null);
  const [checkedFixes, setCheckedFixes] = useState<Set<string>>(new Set());

  const hasAIExplanation = !!issue.ai_explanation;
  const hasProposedFixes = (issue.proposed_fixes?.length ?? 0) > 0;
  const hasLogSnippets = (issue.relevant_log_snippets?.length ?? 0) > 0;
  const hasRichContent = hasAIExplanation || hasProposedFixes;
  const fixCount = issue.proposed_fixes?.length ?? 0;
  const confidencePct = Math.round((issue.ai_confidence ?? 0) * 100);

  const cfg = severityConfig[issue.severity] ?? severityConfig.info;

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedCommand(text);
    setTimeout(() => setCopiedCommand(null), 2000);
  };

  const toggleFix = (fixId: string) => {
    setCheckedFixes((prev) => {
      const next = new Set(prev);
      if (next.has(fixId)) next.delete(fixId);
      else next.add(fixId);
      return next;
    });
  };

  return (
    <div
      className={clsx(
        'bg-navy-700 border border-navy-600 rounded-xl overflow-hidden transition-all duration-200 border-l-4',
        cfg.border,
        expanded && 'ring-1 ring-accent-blue/30'
      )}
    >
      {/* Collapsed header */}
      <button
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-label={`${expanded ? 'Collapse' : 'Expand'} issue: ${issue.title}`}
        className="w-full flex items-center gap-4 p-4 text-left hover:bg-navy-600/50 transition-colors"
      >
        <SeverityIcon severity={issue.severity} />

        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-white truncate">{issue.title}</p>
          {issue.ai_explanation?.root_cause && (
            <div className="mt-1">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">Findings / Technical Root Cause</span>
              <p className="text-xs text-gray-400 line-clamp-2 mt-0.5">{issue.ai_explanation.root_cause}</p>
            </div>
          )}
          <div className="flex items-center gap-2 mt-1.5">
            {issue.resource && (
              <span className="flex items-center gap-1 text-[10px] text-gray-500 bg-navy-800 px-2 py-0.5 rounded">
                <Box size={10} />
                {issue.resource}
              </span>
            )}
            <span className="flex items-center gap-1 text-[10px] text-gray-500 bg-navy-800 px-2 py-0.5 rounded">
              <Tag size={10} />
              {issue.category}
            </span>
            {fixCount > 0 && (
              <span className="flex items-center gap-1 text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded">
                <Wrench size={10} />
                {fixCount} {fixCount === 1 ? 'fix' : 'fixes'}
              </span>
            )}
          </div>
        </div>

        {/* Right: confidence + chevron */}
        <div className="flex items-center gap-3 shrink-0">
          {(issue.ai_confidence ?? 0) > 0 && (
            <div className="text-right">
              <p className="text-lg font-bold text-gray-200">{confidencePct}%</p>
              <p className="text-[10px] text-gray-500">confidence</p>
            </div>
          )}
          {expanded ? (
            <ChevronDown size={16} className="text-gray-400" />
          ) : (
            <ChevronRight size={16} className="text-gray-400" />
          )}
        </div>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-navy-600">
          <div className="pt-4">
            <h4 className="text-xs font-semibold uppercase text-gray-500 mb-2">Description</h4>
            <p className="text-sm text-gray-300 leading-relaxed">{issue.description}</p>
          </div>

          {/* Two-column layout on desktop */}
          <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Left column: AI Evidence Snippets */}
            <div className="space-y-4">
              {/* AI Explanation */}
              {hasAIExplanation && (
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 bg-purple-500/20 rounded-md flex items-center justify-center">
                      <Brain size={14} className="text-purple-400" />
                    </div>
                    <h4 className="text-sm font-semibold text-white">AI Explanation</h4>
                  </div>

                  <div className="bg-navy-800 border border-navy-600 rounded-lg p-3">
                    <p className="text-xs font-semibold uppercase text-gray-500 mb-1">Root Cause</p>
                    <p className="text-sm text-gray-300 leading-relaxed">{issue.ai_explanation?.root_cause}</p>
                  </div>

                  <div className="border-l-2 border-amber-400 bg-amber-500/5 rounded-r-lg p-3">
                    <p className="text-xs font-semibold uppercase text-gray-500 mb-1">Impact</p>
                    <p className="text-sm text-gray-300 leading-relaxed">{issue.ai_explanation?.impact}</p>
                  </div>

                  {(issue.ai_explanation?.related_issues?.length ?? 0) > 0 && (
                    <div>
                      <p className="text-xs font-semibold uppercase text-gray-500 mb-2">Related Issues</p>
                      <div className="flex flex-wrap gap-1.5">
                        {issue.ai_explanation?.related_issues.map((ri, i) => (
                          <span
                            key={i}
                            className="text-xs text-gray-400 bg-navy-800 border border-navy-600 px-2 py-0.5 rounded-full"
                          >
                            {ri}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Log Snippets - AI Evidence */}
              {hasLogSnippets && (
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 bg-blue-500/20 rounded-md flex items-center justify-center">
                      <Terminal size={14} className="text-blue-400" />
                    </div>
                    <h4 className="text-sm font-semibold text-white">AI Evidence Snippets</h4>
                  </div>

                  <div className="space-y-3">
                    {issue.relevant_log_snippets?.map((snippet, si) => (
                      <div key={si}>
                        <p className="text-xs text-gray-500 mb-1 font-mono">{snippet.source}</p>
                        <div className="bg-[#0d1117] rounded-lg p-3 overflow-x-auto">
                          {snippet.lines.map((line, li) => {
                            const isHighlighted = snippet.highlight_indices?.includes(li);
                            const level = snippet.level?.toLowerCase();
                            const lineColor =
                              level === 'error' ? 'text-red-400' :
                              level === 'warn' || level === 'warning' ? 'text-amber-400' :
                              level === 'info' ? 'text-blue-400' :
                              'text-gray-400';
                            return (
                              <pre
                                key={li}
                                className={clsx(
                                  'text-xs font-mono whitespace-pre-wrap leading-5',
                                  lineColor,
                                  isHighlighted && 'bg-white/5 -mx-3 px-3'
                                )}
                              >
                                {line}
                              </pre>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Evidence (fallback) */}
              {!hasRichContent && issue.evidence.length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold uppercase text-gray-500 mb-2">Evidence</h4>
                  <div className="bg-navy-900 rounded-lg p-3 overflow-x-auto">
                    {issue.evidence.map((line, i) => (
                      <pre key={i} className="text-xs text-gray-400 font-mono whitespace-pre-wrap">
                        {line}
                      </pre>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Right column: Recommended Remediation */}
            <div className="space-y-4">
              {/* Proposed Fixes */}
              {hasProposedFixes && (
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 bg-emerald-500/20 rounded-md flex items-center justify-center">
                      <CheckCircle size={14} className="text-emerald-400" />
                    </div>
                    <h4 className="text-sm font-semibold text-white">Recommended Remediation</h4>
                  </div>

                  <div className="space-y-2">
                    {issue.proposed_fixes?.map((fix) => (
                      <div key={fix.id} className="space-y-1.5">
                        <label className="flex items-start gap-2 cursor-pointer group">
                          <input
                            type="checkbox"
                            checked={checkedFixes.has(fix.id)}
                            onChange={() => toggleFix(fix.id)}
                            className="mt-0.5 rounded border-navy-500 bg-navy-800 text-accent-blue focus:ring-accent-blue/30"
                          />
                          <span className="text-sm text-gray-300 group-hover:text-gray-200 transition-colors">
                            {fix.description}
                          </span>
                        </label>
                        {fix.command && (
                          <div className="ml-6 relative bg-[#0d1117] rounded-lg p-3 font-mono text-xs text-gray-300 overflow-x-auto">
                            <button
                              onClick={() => copyToClipboard(fix.command!)}
                              className="absolute top-2 right-2 p-1 rounded hover:bg-navy-700 text-gray-500 hover:text-gray-300 transition-colors"
                              title="Copy command"
                              aria-label="Copy command to clipboard"
                            >
                              <Copy size={12} />
                            </button>
                            <code>{fix.command}</code>
                            {copiedCommand === fix.command && (
                              <span className="absolute top-2 right-8 text-xs text-emerald-400">Copied!</span>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  <button className="mt-1 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium rounded-lg transition-colors">
                    Apply Suggested Fix
                  </button>
                </div>
              )}

              {/* Remediation text (always shown) */}
              <div>
                <h4 className="text-xs font-semibold uppercase text-gray-500 mb-2">Remediation</h4>
                <p className="text-sm text-emerald-400/90 leading-relaxed">{issue.remediation}</p>
              </div>

              {/* AI Confidence bar */}
              <div>
                <h4 className="text-xs font-semibold uppercase text-gray-500 mb-2">AI Confidence</h4>
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-2 bg-navy-900 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${(issue.ai_confidence ?? 0) * 100}%`,
                        backgroundColor:
                          (issue.ai_confidence ?? 0) > 0.7
                            ? '#10b981'
                            : (issue.ai_confidence ?? 0) > 0.4
                              ? '#f59e0b'
                              : '#ef4444',
                      }}
                    />
                  </div>
                  <span className="text-xs text-gray-400 font-mono">
                    {confidencePct}%
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
