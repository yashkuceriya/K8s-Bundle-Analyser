import { Brain } from 'lucide-react';

interface Props {
  insights: string[];
}

export default function AIInsightsCard({ insights }: Props) {
  if (insights.length === 0) return null;

  return (
    <div className="bg-navy-700 border border-navy-600 rounded-xl p-6 border-l-4 border-l-purple-500">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 bg-purple-500/20 rounded-lg flex items-center justify-center">
          <Brain size={18} className="text-purple-400" />
        </div>
        <h3 className="text-base font-semibold text-white">AI Bundle Insights</h3>
      </div>
      <ul className="space-y-2">
        {insights.map((insight, i) => (
          <li key={i} className="flex items-start gap-2.5 text-sm text-gray-300 leading-relaxed">
            <span className="mt-2 w-1.5 h-1.5 rounded-full bg-purple-400 shrink-0" />
            {insight}
          </li>
        ))}
      </ul>
    </div>
  );
}
