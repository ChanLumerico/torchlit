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
        <div className="w-full bg-[#0b0f19]/90 border-b border-slate-800/80 px-8 py-4 shrink-0 flex flex-col gap-4">
            {expsWithProgress.map(exp => {
                const totalSteps = modelInfos[exp].total_steps!;
                const metrics = allMetrics[exp] || [];
                const currentStep = metrics.length > 0 ? metrics[metrics.length - 1].step : 0;
                const progress = Math.min((currentStep / totalSteps) * 100, 100);

                return (
                    <div key={exp} className="w-full flex flex-col">
                        <div className="flex items-center justify-between text-xs text-slate-400 mb-2 font-medium tracking-wide">
                            <span className="uppercase text-slate-300">{exp} <span className="text-slate-500">Progress</span></span>
                            <span>{currentStep.toLocaleString()} / {totalSteps.toLocaleString()} Steps <span className="text-brand ml-1">({progress.toFixed(1)}%)</span></span>
                        </div>
                        <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                            <div
                                className="bg-gradient-to-r from-blue-500 via-indigo-500 to-brand h-1.5 rounded-full transition-all duration-300 ease-out relative"
                                style={{ width: `${progress}%` }}
                            >
                                <div className="absolute top-0 right-0 bottom-0 w-10 bg-gradient-to-l from-white/20 to-transparent blur-[2px]" />
                            </div>
                        </div>
                    </div>
                );
            })}
        </div>
    );
};
