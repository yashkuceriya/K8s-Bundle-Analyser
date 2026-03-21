import { useMemo } from 'react';

interface HealthScoreProps {
  score: number;
  size?: number;
  trend?: number[];
}

export default function HealthScore({ score, size = 160, trend }: HealthScoreProps) {
  const { color, label } = useMemo(() => {
    if (score > 70) return { color: '#10b981', label: 'EXCELLENT' };
    if (score > 40) return { color: '#f59e0b', label: 'MODERATE' };
    return { color: '#ef4444', label: 'CRITICAL' };
  }, [score]);

  const strokeWidth = size >= 100 ? 12 : size >= 60 ? 8 : 6;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;

  const fontSize = size >= 100 ? 'text-5xl' : size >= 60 ? 'text-xl' : 'text-sm';
  const labelSize = size >= 100 ? 'text-xs' : 'text-[8px]';

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
            style={{ filter: `drop-shadow(0 0 8px ${color}50)` }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center rounded-full">
          <span className={`${fontSize} font-bold tracking-tight text-white`}>
            {Math.round(score)}
          </span>
          {size >= 60 && (
            <span className={`${labelSize} font-bold tracking-wider mt-0.5`} style={{ color }}>
              {label}
            </span>
          )}
        </div>
      </div>
      {sparklinePath && (
        <div className="flex flex-col items-center -mt-1">
          <svg width={sparklinePath.w} height={sparklinePath.h} className="overflow-visible">
            <path d={sparklinePath.d} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" opacity="0.6" />
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
