import clsx from 'clsx';

interface SeverityBadgeProps {
  severity: string;
  className?: string;
}

const styles: Record<string, string> = {
  critical: 'bg-red-500/20 text-red-400 border border-red-500/30',
  warning: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  info: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
  error: 'bg-red-500/20 text-red-400 border border-red-500/30',
  warn: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  healthy: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
};

export default function SeverityBadge({ severity, className }: SeverityBadgeProps) {
  const key = severity.toLowerCase();
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium',
        styles[key] || 'bg-gray-500/20 text-gray-400 border border-gray-500/30',
        className
      )}
    >
      <span
        className={clsx('w-1.5 h-1.5 rounded-full', {
          'bg-red-400': key === 'critical' || key === 'error',
          'bg-amber-400': key === 'warning' || key === 'warn',
          'bg-blue-400': key === 'info',
          'bg-emerald-400': key === 'healthy',
          'bg-gray-400': !styles[key],
        })}
      />
      {severity.charAt(0).toUpperCase() + severity.slice(1).toLowerCase()}
    </span>
  );
}
