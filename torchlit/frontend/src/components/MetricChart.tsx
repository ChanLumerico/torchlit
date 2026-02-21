import React from 'react';
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Legend
} from 'recharts';

interface MetricChartProps {
    title: string;
    data: any[];
    dataKey: string;
    color: string;
    smoothing: number;
}

export const MetricChart: React.FC<MetricChartProps> = ({ title, data, dataKey, color, smoothing }) => {
    // Compute EMA for the data
    const smoothedData = React.useMemo(() => {
        if (smoothing === 0) return data;

        const result: any[] = [];
        let prevSmoothed: number | null = null;

        for (const item of data) {
            const val = item[dataKey];
            if (val === undefined || val === null) {
                result.push({ ...item });
                continue;
            }

            if (prevSmoothed === null) {
                prevSmoothed = val;
            } else {
                prevSmoothed = prevSmoothed * smoothing + val * (1 - smoothing);
            }

            result.push({
                ...item,
                [`${dataKey}_smoothed`]: prevSmoothed
            });
        }
        return result;
    }, [data, dataKey, smoothing]);

    return (
        <div className="bg-slate-800/80 backdrop-blur-sm border border-slate-700/50 p-5 rounded-2xl shadow-xl hover:shadow-2xl transition-all duration-300">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                    {title}
                </h3>
            </div>
            <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={smoothedData} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                        <XAxis
                            dataKey="step"
                            stroke="#64748b"
                            tick={{ fill: '#64748b', fontSize: 12 }}
                            tickLine={false}
                            axisLine={false}
                        />
                        <YAxis
                            stroke="#64748b"
                            tick={{ fill: '#64748b', fontSize: 12 }}
                            tickLine={false}
                            axisLine={false}
                            domain={['auto', 'auto']}
                        />
                        <Tooltip
                            contentStyle={{
                                backgroundColor: '#0f172a',
                                border: '1px solid #334155',
                                borderRadius: '0.75rem',
                                boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)'
                            }}
                            itemStyle={{ color: '#f8fafc' }}
                            labelStyle={{ color: '#94a3b8', marginBottom: '4px' }}
                        />
                        <Legend verticalAlign="top" height={36} iconType="circle" />

                        {/* Faint Raw Line */}
                        {smoothing > 0 && (
                            <Line
                                name={`${title} (raw)`}
                                type="monotone"
                                dataKey={dataKey}
                                stroke={color}
                                strokeWidth={1}
                                strokeOpacity={0.3}
                                dot={false}
                                activeDot={false}
                                isAnimationActive={false}
                            />
                        )}

                        {/* Bold Smoothed Line */}
                        <Line
                            name={smoothing > 0 ? `${title} (smooth)` : title}
                            type="monotone"
                            dataKey={smoothing > 0 ? `${dataKey}_smoothed` : dataKey}
                            stroke={color}
                            strokeWidth={3}
                            dot={false}
                            activeDot={{ r: 6, strokeWidth: 0, fill: color }}
                            animationDuration={300}
                        />
                    </LineChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
};
