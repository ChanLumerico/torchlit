import React from 'react';
import { AreaChart, Area, ResponsiveContainer } from 'recharts';
import type { SysStats } from '../types';

interface SparklineProps {
    data: SysStats[];
    dataKey: string;
    color: string;
}

export const Sparkline: React.FC<SparklineProps> = ({ data, dataKey, color }) => {
    if (!data || data.length === 0) return null;

    // Generate simple array of objects for recharts
    const chartData = data.map((d, i) => ({ index: i, value: d[dataKey as keyof SysStats] || 0 }));

    return (
        <div className="absolute -left-2 -right-2 -bottom-2 top-10 opacity-20 pointer-events-none">
            <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                    <defs>
                        <linearGradient id={`grad-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={color} stopOpacity={0.8} />
                            <stop offset="100%" stopColor={color} stopOpacity={0.15} />
                        </linearGradient>
                    </defs>
                    <Area
                        type="monotone"
                        dataKey="value"
                        stroke={color}
                        fillOpacity={1}
                        fill={`url(#grad-${dataKey})`}
                        strokeWidth={2}
                        isAnimationActive={false}
                    />
                </AreaChart>
            </ResponsiveContainer>
        </div>
    );
};
