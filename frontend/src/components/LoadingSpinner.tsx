import { Loader2 } from 'lucide-react';
import clsx from 'clsx';

interface LoadingSpinnerProps {
  size?: number;
  className?: string;
  label?: string;
}

export default function LoadingSpinner({ size = 24, className, label }: LoadingSpinnerProps) {
  return (
    <div className={clsx('flex flex-col items-center justify-center gap-3', className)}>
      <Loader2 size={size} className="animate-spin text-accent-blue" />
      {label && <p className="text-gray-400 text-sm">{label}</p>}
    </div>
  );
}
