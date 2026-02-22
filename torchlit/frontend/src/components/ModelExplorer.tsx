import React, { useState } from 'react';
import { Layers, ChevronDown, ChevronRight, Hash, Box } from 'lucide-react';
import type { ModelInfo, ArchitectureNode } from '../types';

interface ModelExplorerProps {
    modelInfo: ModelInfo | null;
}

const formatNumber = (num: number) => {
    if (num >= 1e9) return `${(num / 1e9).toFixed(1)}B`;
    if (num >= 1e6) return `${(num / 1e6).toFixed(1)}M`;
    if (num >= 1e3) return `${(num / 1e3).toFixed(1)}K`;
    return num.toString();
};

const getModuleColor = (className: string) => {
    const name = className.toLowerCase();
    if (name.includes('conv')) return 'text-indigo-400 bg-indigo-400/10 border-indigo-400/20';
    if (name.includes('linear')) return 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20';
    if (['sequential', 'modulelist', 'moduledict'].some(c => name.includes(c)))
        return 'text-amber-400 bg-amber-400/10 border-amber-400/20';
    if (['relu', 'sigmoid', 'tanh', 'gelu', 'softmax'].some(c => name.includes(c)))
        return 'text-rose-400 bg-rose-400/10 border-rose-400/20';
    if (name.includes('norm')) return 'text-cyan-400 bg-cyan-400/10 border-cyan-400/20';
    if (name.includes('pool')) return 'text-violet-400 bg-violet-400/10 border-violet-400/20';
    return 'text-brand/80 bg-brand/10 border-brand/20';
};

const TreeNode: React.FC<{ node: ArchitectureNode; depth: number }> = ({ node, depth }) => {
    const hasChildren = node.children && node.children.length > 0;
    const [isExpanded, setIsExpanded] = useState(depth < 2); // Auto-expand first 2 levels
    const colorClass = getModuleColor(node.class_name);

    return (
        <div className="flex flex-col">
            <div
                className={`flex items-center gap-2 py-2 px-3 hover:bg-slate-800/50 rounded-lg group transition-colors ${hasChildren ? 'cursor-pointer' : ''}`}
                style={{ paddingLeft: `${depth * 1.5 + 0.75}rem` }}
                onClick={() => hasChildren && setIsExpanded(!isExpanded)}
            >
                <div className="w-4 h-4 text-slate-500 shrink-0 flex items-center justify-center">
                    {hasChildren ? (
                        isExpanded ? <ChevronDown className="w-4 h-4 hover:text-white" /> : <ChevronRight className="w-4 h-4 hover:text-white" />
                    ) : (
                        <div className="w-1.5 h-1.5 rounded-full bg-slate-700" />
                    )}
                </div>

                <div className="flex-1 flex flex-wrap items-center gap-x-3 gap-y-1 min-w-0">
                    <span className="text-slate-300 font-mono text-sm truncate">{node.name}</span>
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-md border shrink-0 transition-colors ${colorClass}`}>
                        {node.class_name}
                    </span>
                </div>

                <div className="flex items-center gap-3 shrink-0 ml-4">
                    {node.params > 0 && (
                        <span className="text-emerald-400 text-xs font-mono tabular-nums flex items-center gap-1 opacity-60 group-hover:opacity-100 transition-opacity" title="Direct Layer Parameters">
                            <Hash className="w-3 h-3" />
                            {formatNumber(node.params)}
                        </span>
                    )}
                    {node.total_params > 0 && node.total_params !== node.params && (
                        <span className="text-slate-400 text-xs font-mono tabular-nums bg-slate-800 px-2 py-1 rounded-md min-w-[4rem] text-right" title="Total Nested Parameters">
                            {formatNumber(node.total_params)}
                        </span>
                    )}
                </div>
            </div>

            {hasChildren && isExpanded && (
                <div className="flex flex-col border-l border-slate-800/60 ml-3">
                    {node.children.map((child, idx) => (
                        <TreeNode key={`${child.name}-${idx}`} node={child} depth={depth + 1} />
                    ))}
                </div>
            )}
        </div>
    );
};

export const ModelExplorer: React.FC<ModelExplorerProps> = ({ modelInfo }) => {
    if (!modelInfo) {
        return (
            <div className="h-96 flex flex-col items-center justify-center text-slate-500 bg-slate-800/20 border border-slate-800 rounded-3xl border-dashed">
                <Box className="w-12 h-12 mb-4 opacity-50" />
                <p className="text-lg font-medium">No Model Data Available</p>
                <p className="text-sm">Connect a PyTorch module to view its architecture.</p>
            </div>
        );
    }

    return (
        <div className="bg-slate-900/40 border border-slate-800/80 rounded-3xl overflow-hidden flex flex-col h-[calc(100vh-12rem)] shadow-xl">
            <div className="p-6 border-b border-slate-800/80 bg-slate-900/80 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-3">
                    <div className="bg-emerald-500/20 p-2.5 rounded-xl border border-emerald-500/20">
                        <Layers className="text-emerald-400 w-6 h-6" />
                    </div>
                    <div>
                        <h2 className="text-xl font-bold text-slate-100">{modelInfo.name}</h2>
                        <p className="text-sm text-slate-400 font-medium">Interactive Architecture Tree</p>
                    </div>
                </div>

                <div className="flex items-center gap-4">
                    <div className="flex flex-col items-end">
                        <span className="text-xs text-slate-500 uppercase font-bold tracking-wider">Total Params</span>
                        <span className="text-lg font-semibold text-slate-200">{modelInfo.total_params}</span>
                    </div>
                    <div className="h-8 w-px bg-slate-800"></div>
                    <div className="flex flex-col items-end">
                        <span className="text-xs text-slate-500 uppercase font-bold tracking-wider">Trainable</span>
                        <span className="text-lg font-semibold text-emerald-400">{modelInfo.trainable_params}</span>
                    </div>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                {modelInfo.architecture ? (
                    <div className="bg-[#0b0f19] rounded-2xl p-4 border border-slate-800/50 shadow-inner">
                        <TreeNode node={modelInfo.architecture} depth={0} />
                    </div>
                ) : (
                    <div className="h-full flex flex-col items-center justify-center text-slate-500">
                        <p>Detailed architecture tree not captured.</p>
                    </div>
                )}
            </div>
        </div>
    );
};
