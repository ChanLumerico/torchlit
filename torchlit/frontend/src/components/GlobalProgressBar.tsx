import React from 'react';
import type { ModelInfo } from '../types';

interface GlobalProgressBarProps {
    selectedExps: string[];
    allMetrics: Record<string, any[]>;
    modelInfos: Record<string, ModelInfo>;
}

export const GlobalProgressBar: React.FC<GlobalProgressBarProps> = ({ selectedExps, allMetrics, modelInfos }) => {
    // Only show progress for experiments that have a defined total_steps
    const expsWithProgress = selectedExps.filter(exp => {
        const info = modelInfos[exp];
        return info && info.total_steps && info.total_steps > 0;
    });

    if (expsWithProgress.length === 0) return null;

    return (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-[100] flex flex-col gap-3 pointer-events-none">
            {expsWithProgress.map(exp => {
                const totalSteps = modelInfos[exp].total_steps!;
                const metrics = allMetrics[exp] || [];
                const currentStep = metrics.length > 0 ? metrics[metrics.length - 1].step : 0;
                const progress = Math.min((currentStep / totalSteps) * 100, 100);

                return (
                    <div
                        key={exp}
                        className="pointer-events-auto flex items-center gap-4 bg-slate-900/90 backdrop-blur-md border border-slate-700/50 rounded-full px-5 py-2.5 shadow-2xl shadow-brand/10 hover:scale-[1.02] hover:shadow-brand/20 transition-all duration-300 pointer-events-auto group"
                    >
                        {/* Glow indicator & Exp Name */}
                        <div className="flex items-center gap-2 shrink-0">
                            <span className="w-2 h-2 rounded-full bg-brand animate-pulse shadow-[0_0_8px_rgba(249,115,22,0.8)]" />
                            <span className="text-sm font-semibold text-slate-200 truncate max-w-[120px]" title={exp}>{exp}</span>
                        </div>

                        {/* Compact Thin Progress Bar */}
                        <div className="w-48 bg-slate-800 rounded-full h-1.5 overflow-hidden shadow-inner flex shrink-0 group-hover:h-2 transition-all duration-300">
                            <div
                                className="bg-gradient-to-r from-orange-400 via-brand to-rose-500 h-full rounded-full transition-all duration-300 ease-out relative"
                                style={{ width: `${progress}%` }}
                            >
                                <div className="absolute top-0 right-0 bottom-0 w-8 bg-gradient-to-l from-white/40 to-transparent blur-[1px]" />
                            </div>
                        </div>

                        {/* Step counts & Percentage */}
                        <div className="flex items-center gap-2 shrink-0 text-xs font-medium tracking-wide">
                            <span className="text-slate-400">{currentStep.toLocaleString()} <span className="text-slate-600">/</span> {totalSteps.toLocaleString()}</span>
                            <span className="text-brand w-10 text-right">{progress.toFixed(1)}%</span>
                        </div>
                    </div>
                );
            })}
        </div>
    );
};
