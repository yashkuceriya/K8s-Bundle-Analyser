import { useMemo, useState } from 'react';
import type { ResourceHealthDot } from '../types';

interface Props {
  resourceHealth: ResourceHealthDot[];
}

const statusColor = (status: string): string => {
  const s = status.toLowerCase();
  if (s === 'healthy' || s === 'running' || s === 'ready') return 'bg-emerald-400';
  if (s === 'warning' || s === 'pending') return 'bg-amber-400';
  if (s === 'critical' || s === 'error' || s === 'failed' || s === 'crashloopbackoff') return 'bg-red-400';
  return 'bg-gray-500';
};

const statusLabel = (status: string): string => {
  const s = status.toLowerCase();
  if (s === 'healthy' || s === 'running' || s === 'ready') return 'healthy';
  if (s === 'warning' || s === 'pending') return 'warning';
  if (s === 'critical' || s === 'error' || s === 'failed' || s === 'crashloopbackoff') return 'critical';
  return 'unknown';
};

export default function ClusterHealthGrid({ resourceHealth }: Props) {
  const [hoveredDot, setHoveredDot] = useState<ResourceHealthDot | null>(null);
  const [hoverPos, setHoverPos] = useState({ x: 0, y: 0 });

  const grouped = useMemo(() => {
    const groups: Record<string, ResourceHealthDot[]> = {};
    for (const dot of resourceHealth) {
      const key = dot.type;
      if (!groups[key]) groups[key] = [];
      groups[key].push(dot);
    }
    return groups;
  }, [resourceHealth]);

  const groupOrder = ['Node', 'Deployment', 'StatefulSet', 'DaemonSet', 'Job', 'Pod', 'Service', 'Ingress'];

  const sortedKeys = useMemo(() => {
    const keys = Object.keys(grouped);
    return keys.sort((a, b) => {
      const ai = groupOrder.findIndex((g) => a.toLowerCase().includes(g.toLowerCase()));
      const bi = groupOrder.findIndex((g) => b.toLowerCase().includes(g.toLowerCase()));
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
    });
  }, [grouped]);

  if (resourceHealth.length === 0) return null;

  const handleDotHover = (dot: ResourceHealthDot, e: React.MouseEvent) => {
    const rect = (e.currentTarget as HTMLElement).closest('.health-grid-container')?.getBoundingClientRect();
    if (rect) {
      setHoverPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
    }
    setHoveredDot(dot);
  };

  return (
    <div className="health-grid-container relative bg-navy-700 border border-navy-600 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-semibold text-white">Cluster Resource Health</h3>
        <span className="text-xs text-gray-500">{resourceHealth.length} resources</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {sortedKeys.map((type) => {
          const dots = grouped[type];
          const counts: Record<string, number> = {};
          for (const d of dots) {
            const label = statusLabel(d.status);
            counts[label] = (counts[label] ?? 0) + 1;
          }
          const total = dots.length;

          return (
            <div key={type} className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-gray-300">{type}s</p>
                <span className="text-xs text-gray-500">{total}</span>
              </div>
              {/* Health bar */}
              <div className="w-full h-1.5 bg-navy-900 rounded-full overflow-hidden flex">
                {counts.healthy ? <div className="h-full bg-emerald-400" style={{ width: `${(counts.healthy / total) * 100}%` }} /> : null}
                {counts.warning ? <div className="h-full bg-amber-400" style={{ width: `${(counts.warning / total) * 100}%` }} /> : null}
                {counts.critical ? <div className="h-full bg-red-400" style={{ width: `${(counts.critical / total) * 100}%` }} /> : null}
                {counts.unknown ? <div className="h-full bg-gray-500" style={{ width: `${(counts.unknown / total) * 100}%` }} /> : null}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {dots.map((dot) => (
                  <div
                    key={dot.id}
                    className={`w-4 h-4 rounded-full ${statusColor(dot.status)} cursor-pointer transition-all duration-150 hover:scale-125 hover:ring-2 hover:ring-white/20`}
                    onMouseEnter={(e) => handleDotHover(dot, e)}
                    onMouseLeave={() => setHoveredDot(null)}
                  />
                ))}
              </div>
              <div className="flex flex-wrap gap-2 text-xs text-gray-500">
                {counts.healthy ? (
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-emerald-400" />
                    {counts.healthy} healthy
                  </span>
                ) : null}
                {counts.warning ? (
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-amber-400" />
                    {counts.warning} warning
                  </span>
                ) : null}
                {counts.critical ? (
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-red-400" />
                    {counts.critical} critical
                  </span>
                ) : null}
                {counts.unknown ? (
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-gray-500" />
                    {counts.unknown} unknown
                  </span>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      {/* Hover tooltip */}
      {hoveredDot && (
        <div
          className="absolute z-30 pointer-events-none bg-navy-800 border border-navy-600 rounded-lg px-3 py-2 shadow-xl"
          style={{ left: hoverPos.x + 12, top: hoverPos.y - 40 }}
        >
          <p className="text-xs font-semibold text-white">{hoveredDot.name}</p>
          <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-400">
            <span className={`w-2 h-2 rounded-full ${statusColor(hoveredDot.status)}`} />
            <span>{hoveredDot.status}</span>
            {hoveredDot.namespace && <span className="text-gray-600">ns: {hoveredDot.namespace}</span>}
          </div>
        </div>
      )}
    </div>
  );
}
