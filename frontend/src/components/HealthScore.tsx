import { useMemo } from 'react';

interface HealthScoreProps {
  score: number;
  size?: number;
  trend?: number[];
}

export default function HealthScore({ score, size = 160, trend }: HealthScoreProps) {
  const { color, bgColor, label } = useMemo(() => {
    if (score > 70) return { color: '#06b6d4', bgColor: 'rgba(6,182,212,0.12)', label: 'Healthy' };
    if (score > 40) return { color: '#f59e0b', bgColor: 'rgba(245,158,11,0.12)', label: 'Degraded' };
    return { color: '#ef4444', bgColor: 'rgba(239,68,68,0.12)', label: 'Critical' };
  }, [score]);

  const strokeWidth = 10;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;

  const displayScore = Number.isInteger(score) ? `${score}%` : `${score.toFixed(1)}%`;

  // Mini sparkline SVG path from trend data
  const sparklinePath = useMemo(() => {
    if (!trend || trend.length < 2) return null;
    const w = size * 0.7;
    const h = 24;
    const min = Math.min(...trend);
    const max = Math.max(...trend);
    const range = max - min || 1;
    const step = w / (trend.length - 1);
    const points = trend.map((v, i) => `${i * step},${h - ((v - min) / range) * h}`);
    return { d: `M${points.join(' L')}`, w, h };
  }, [trend, size]);

  return (
    <div className="flex flex-col items-center gap-1">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">System Health</p>
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="#1a2332"
            strokeWidth={strokeWidth}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={circumference - progress}
            strokeLinecap="round"
            className="transition-all duration-1000 ease-out"
            style={{ filter: `drop-shadow(0 0 6px ${color}40)` }}
          />
        </svg>
        <div
          className="absolute inset-0 flex flex-col items-center justify-center rounded-full"
          style={{ backgroundColor: bgColor }}
        >
          <span className="text-4xl font-bold tracking-tight" style={{ color }}>
            {displayScore}
          </span>
          <span className="text-xs text-gray-400 font-medium mt-0.5">{label}</span>
        </div>
      </div>
      {/* Trend sparkline */}
      {sparklinePath && (
        <div className="flex flex-col items-center -mt-1">
          <svg width={sparklinePath.w} height={sparklinePath.h} className="overflow-visible">
            <path
              d={sparklinePath.d}
              fill="none"
              stroke={color}
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity="0.6"
            />
            {/* Last point dot */}
            {trend && trend.length > 0 && (() => {
              const w = sparklinePath.w;
              const h = sparklinePath.h;
              const min = Math.min(...trend);
              const max = Math.max(...trend);
              const range = max - min || 1;
              const step = w / (trend.length - 1);
              const lastX = (trend.length - 1) * step;
              const lastY = h - ((trend[trend.length - 1] - min) / range) * h;
              return <circle cx={lastX} cy={lastY} r="2.5" fill={color} />;
            })()}
          </svg>
          <span className="text-[9px] text-gray-600 mt-0.5">{trend!.length} runs</span>
        </div>
      )}
    </div>
  );
}
