import React from 'react';
import { Layers } from 'lucide-react';

interface ComparisonTableProps {
    selectedExps: string[];
    allMetrics: Record<string, any[]>;
    metricKeys: string[];
}

export const ComparisonTable: React.FC<ComparisonTableProps> = ({ selectedExps, allMetrics, metricKeys }) => {
    if (selectedExps.length === 0 || metricKeys.length === 0) return null;

    // Get the latest value for each metric in each session
    const getLatestValue = (exp: string, metric: string) => {
        const logs = allMetrics[exp];
        if (!logs || logs.length === 0) return '--';

        // Find the last log entry that has this metric
        for (let i = logs.length - 1; i >= 0; i--) {
            if (logs[i][metric] !== undefined) {
                return typeof logs[i][metric] === 'number'
                    ? logs[i][metric].toFixed(4)
                    : logs[i][metric];
            }
        }
        return '--';
    };

    return (
        <div className="bg-slate-900/50 border border-slate-700/50 rounded-3xl overflow-hidden mt-8">
            <div className="px-6 py-4 border-b border-slate-700/50 flex items-center gap-3 bg-slate-800/20">
                <Layers className="text-brand w-5 h-5" />
                <h3 className="text-lg font-semibold text-slate-200">Session Data Comparison</h3>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-left text-sm text-slate-400">
                    <thead className="text-xs uppercase bg-slate-800/50 text-slate-500 font-bold tracking-wider">
                        <tr>
                            <th className="px-6 py-4">Metric</th>
                            {selectedExps.map(exp => (
                                <th key={exp} className="px-6 py-4 text-brand">{exp}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {metricKeys.map((metric, idx) => (
                            <tr key={metric} className={`border-b border-slate-700/50 hover:bg-slate-800/30 transition-colors ${idx % 2 === 0 ? 'bg-slate-900/20' : ''}`}>
                                <th scope="row" className="px-6 py-4 font-medium text-slate-200 whitespace-nowrap">
                                    {metric}
                                </th>
                                {selectedExps.map(exp => (
                                    <td key={exp} className="px-6 py-4 font-mono">
                                        {getLatestValue(exp, metric)}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};
