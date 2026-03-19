import { useState, useMemo } from 'react';
import { ChevronDown, ChevronRight, GitBranch } from 'lucide-react';
import { AreaChart, Area, ResponsiveContainer, Tooltip } from 'recharts';
import { format } from 'date-fns';
import clsx from 'clsx';
import type { CorrelationGroup } from '../types';
import SeverityBadge from './SeverityBadge';

interface Props {
  correlations: CorrelationGroup[];
}

export default function LogCorrelationView({ correlations }: Props) {
  const sorted = useMemo(
    () => [...correlations].sort((a, b) => b.events.length - a.events.length),
    [correlations]
  );

  if (correlations.length === 0) {
    return (
      <div className="bg-navy-700 border border-navy-600 rounded-xl p-12 text-center text-gray-500">
        <GitBranch size={40} className="mx-auto mb-3 text-gray-600" />
        <p>No correlated events found</p>
        <p className="text-xs text-gray-600 mt-1">Event correlations will appear here when detected</p>
      </div>
    );
  }

  return (
    <div className="max-w-screen-xl space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <GitBranch size={20} className="text-accent-blue" />
        <h2 className="text-lg font-semibold text-white">Log Correlations</h2>
        <span className="text-xs text-gray-500 ml-2">{sorted.length} groups</span>
      </div>
      {sorted.map((group) => (
        <CorrelationCard key={group.id} group={group} />
      ))}
    </div>
  );
}

function CorrelationCard({ group }: { group: CorrelationGroup }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-navy-700 border border-navy-600 rounded-xl overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-4 text-left hover:bg-navy-600/50 transition-colors"
      >
        <div className="flex items-start gap-3">
          {expanded ? (
            <ChevronDown size={16} className="text-gray-400 mt-0.5 shrink-0" />
          ) : (
            <ChevronRight size={16} className="text-gray-400 mt-0.5 shrink-0" />
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-4">
              <h3 className="text-sm font-bold text-white truncate">{group.title}</h3>
              <span className="text-xs text-gray-500 shrink-0">{group.events.length} events</span>
            </div>
            <p className="text-xs text-gray-400 mt-1 line-clamp-2">{group.explanation}</p>
          </div>
          {group.sparkline_data.length > 0 && (
            <div className="w-[220px] h-[60px] shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={group.sparkline_data}>
                  <defs>
                    <linearGradient id={`spark-${group.id}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      return (
                        <div className="bg-navy-800 border border-navy-600 rounded px-2 py-1 text-[10px] shadow-lg">
                          <span className="text-white font-medium">{payload[0].value} events</span>
                        </div>
                      );
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="count"
                    stroke="#3b82f6"
                    fill={`url(#spark-${group.id})`}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 3, fill: '#3b82f6', stroke: '#0a0e1a', strokeWidth: 2 }}
                    animationDuration={800}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-navy-600 px-4 pb-4 pt-3 space-y-2">
          {group.events.map((event, idx) => (
            <div
              key={`${event.timestamp}-${idx}`}
              className={clsx(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm',
                idx % 2 === 0 ? 'bg-navy-800/50' : 'bg-navy-800/30'
              )}
            >
              <SeverityBadge severity={event.severity} />
              <span className="text-xs text-gray-500 font-mono shrink-0">
                {(() => {
                  try {
                    return format(new Date(event.timestamp), 'HH:mm:ss.SSS');
                  } catch {
                    return event.timestamp;
                  }
                })()}
              </span>
              <span className="text-xs text-gray-300 truncate flex-1">{event.message}</span>
              {event.resource && (
                <span className="text-xs text-gray-500 shrink-0">{event.resource}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
