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
import { Maximize2, Activity } from 'lucide-react';

interface MetricChartProps {
    title: string;
    data: any[];
    selectedExps: string[];
    metricKey: string;
    smoothing: number;
    onZoom?: () => void;
    isZoomed?: boolean;
    colorIndex?: number;
}

export const MetricChart: React.FC<MetricChartProps> = ({
    title,
    data,
    selectedExps,
    metricKey,
    smoothing,
    onZoom,
    isZoomed = false,
    colorIndex = 0
}) => {
    // Modern, soft warm palette starting from orange
    const colors = [
        "#f97316", // Tailwind orange-500
        "#f7b267", // Soft amber/muted gold
        "#f4845f", // Soft coral
        "#f27059", // Terracotta
        "#f6bd60", // Muted sand/yellow
        "#f28482", // Soft pinkish red
        "#f79d65"  // Peach orange
    ];

    // Compute EMA for each selected experiment
    const processedData = React.useMemo(() => {
        if (smoothing === 0) return data;

        const smoothedData = data.map(d => ({ ...d }));

        selectedExps.forEach(exp => {
            const key = `${metricKey}::${exp}`;
            let prevSmoothed: number | null = null;

            for (let i = 0; i < smoothedData.length; i++) {
                const val = smoothedData[i][key];
                if (val === undefined || val === null) continue;

                if (prevSmoothed === null) {
                    prevSmoothed = val;
                } else {
                    prevSmoothed = prevSmoothed * smoothing + val * (1 - smoothing);
                }
                smoothedData[i][`${key}_smoothed`] = prevSmoothed;
            }
        });

        return smoothedData;
    }, [data, metricKey, selectedExps, smoothing]);

    return (
        <div className={`bg-slate-800/80 backdrop-blur-sm border border-slate-700/50 rounded-2xl shadow-xl transition-all duration-300 ${isZoomed ? 'p-8 h-full flex flex-col' : 'p-5 hover:shadow-2xl'}`}>
            <div className="flex items-center justify-between mb-4">
                <h3 className={`${isZoomed ? 'text-lg' : 'text-sm'} font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2`}>
                    <Activity size={isZoomed ? 20 : 16} style={{ color: colors[colorIndex % colors.length] }} />
                    {title}
                </h3>
                {!isZoomed && onZoom && (
                    <button
                        onClick={onZoom}
                        className="p-2 hover:bg-slate-700/50 rounded-lg text-slate-400 hover:text-brand transition-colors"
                        title="Zoom Chart"
                    >
                        <Maximize2 size={16} />
                    </button>
                )}
            </div>
            <div className={`${isZoomed ? 'flex-1 min-h-0' : 'h-64'} w-full`}>
                <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={processedData} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
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

                        {selectedExps.map((exp, idx) => {
                            const key = `${metricKey}::${exp}`;
                            const color = colors[(colorIndex + idx) % colors.length];
                            const dataKey = smoothing > 0 ? `${key}_smoothed` : key;

                            return (
                                <React.Fragment key={exp}>
                                    {/* Faint Raw Line */}
                                    {smoothing > 0 && (
                                        <Line
                                            name={`${exp} (raw)`}
                                            type="monotone"
                                            dataKey={key}
                                            stroke={color}
                                            strokeWidth={1}
                                            strokeOpacity={0.2}
                                            dot={false}
                                            activeDot={false}
                                            isAnimationActive={false}
                                        />
                                    )}
                                    {/* Bold Main Line */}
                                    <Line
                                        name={exp}
                                        type="monotone"
                                        dataKey={dataKey}
                                        stroke={color}
                                        strokeWidth={isZoomed ? 4 : 2}
                                        dot={false}
                                        activeDot={{ r: 6, strokeWidth: 0, fill: color }}
                                        animationDuration={300}
                                    />
                                </React.Fragment>
                            );
                        })}
                    </LineChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
};
