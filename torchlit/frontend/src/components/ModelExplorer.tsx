import React, { useState, useEffect } from 'react';
import { Layers, ChevronDown, ChevronRight, Hash, Box, ChevronsDownUp, ChevronsUpDown, Grid, ArrowRight, Activity, Filter, CircleDot, Database } from 'lucide-react';
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

interface ThemeConfig {
    badge: string;
    icon: React.ElementType;
    iconColor: string;
    rowHover: string;
    borderLeft: string;
}

const getModuleTheme = (className: string): ThemeConfig => {
    const name = className.toLowerCase();

    // Convolutional Layers (Grid pattern)
    if (name.includes('conv')) return {
        badge: 'text-indigo-300 bg-indigo-500/10 border-indigo-500/20',
        icon: Grid,
        iconColor: 'text-indigo-400',
        rowHover: 'hover:bg-indigo-500/5',
        borderLeft: 'border-l-indigo-500/30'
    };

    // Linear / Fully Connected (Data flow arrow)
    if (name.includes('linear')) return {
        badge: 'text-emerald-300 bg-emerald-500/10 border-emerald-500/20',
        icon: ArrowRight,
        iconColor: 'text-emerald-400',
        rowHover: 'hover:bg-emerald-500/5',
        borderLeft: 'border-l-emerald-500/30'
    };

    // Containers / Blocks (Layers/Boxes)
    if (['sequential', 'modulelist', 'moduledict', 'block', 'layer'].some(c => name.includes(c))) return {
        badge: 'text-amber-300 bg-amber-500/10 border-amber-500/20',
        icon: Layers,
        iconColor: 'text-amber-400',
        rowHover: 'hover:bg-amber-500/5',
        borderLeft: 'border-l-amber-500/30'
    };

    // Activations (Non-linear activity)
    if (['relu', 'sigmoid', 'tanh', 'gelu', 'swish', 'silu', 'softmax'].some(c => name.includes(c))) return {
        badge: 'text-rose-300 bg-rose-500/10 border-rose-500/20',
        icon: Activity,
        iconColor: 'text-rose-400',
        rowHover: 'hover:bg-rose-500/5',
        borderLeft: 'border-l-rose-500/30'
    };

    // Normalization (Balancing/Data)
    if (name.includes('norm')) return {
        badge: 'text-cyan-300 bg-cyan-500/10 border-cyan-500/20',
        icon: Database,
        iconColor: 'text-cyan-400',
        rowHover: 'hover:bg-cyan-500/5',
        borderLeft: 'border-l-cyan-500/30'
    };

    // Pooling (Filtering down)
    if (name.includes('pool')) return {
        badge: 'text-violet-300 bg-violet-500/10 border-violet-500/20',
        icon: Filter,
        iconColor: 'text-violet-400',
        rowHover: 'hover:bg-violet-500/5',
        borderLeft: 'border-l-violet-500/30'
    };

    // Custom / Default (Generic dot)
    return {
        badge: 'text-brand/80 bg-brand/10 border-brand/20',
        icon: CircleDot,
        iconColor: 'text-slate-500',
        rowHover: 'hover:bg-slate-800/60',
        borderLeft: 'border-l-slate-700/50'
    };
};

// null = use default, true = force expand all, false = force collapse all
const TreeNode: React.FC<{ node: ArchitectureNode; depth: number; forceExpand: boolean | null }> = ({ node, depth, forceExpand }) => {
    const hasChildren = node.children && node.children.length > 0;
    const [isExpanded, setIsExpanded] = useState(depth < 2);
    const theme = getModuleTheme(node.class_name);
    const IconComponent = theme.icon;

    // Sync with global expand/collapse signal
    useEffect(() => {
        if (forceExpand !== null && hasChildren) {
            setIsExpanded(forceExpand);
        }
    }, [forceExpand, hasChildren]);

    return (
        <div className="flex flex-col relative">
            {/* Visual hierarchy connector line for children depth */}
            {depth > 0 && (
                <div
                    className="absolute top-0 bottom-0 border-l border-slate-800/60 pointer-events-none"
                    style={{ left: `${(depth - 1) * 1.5 + 1.25}rem` }}
                />
            )}

            <div
                className={`flex items-center gap-2 py-2 px-3 rounded-lg group transition-all duration-200 border-l-2 border-transparent ${theme.rowHover} ${hasChildren ? 'cursor-pointer' : ''}`}
                style={{ paddingLeft: `${depth * 1.5 + 0.75}rem` }}
                onClick={() => hasChildren && setIsExpanded(!isExpanded)}
            >
                {/* Expander Arrow */}
                <div className="w-5 h-5 text-slate-500 shrink-0 flex items-center justify-center mr-1">
                    {hasChildren ? (
                        <div className="p-0.5 rounded-md hover:bg-slate-700/50 transition-colors">
                            {isExpanded ? <ChevronDown className="w-4 h-4 text-slate-400 group-hover:text-white" /> : <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-white" />}
                        </div>
                    ) : (
                        <div className="w-1.5 h-1.5 rounded-full bg-slate-700/50" />
                    )}
                </div>

                {/* Module Specific Icon */}
                <div className="shrink-0 flex items-center justify-center w-6 h-6 rounded-md bg-slate-800/40 border border-slate-700/30">
                    <IconComponent className={`w-3.5 h-3.5 ${theme.iconColor}`} />
                </div>

                <div className="flex-1 flex flex-wrap items-center gap-x-3 gap-y-1 min-w-0 ml-1">
                    <span className="text-slate-200 font-mono text-sm shadow-sm font-medium tracking-tight truncate">{node.name}</span>
                    <span className={`text-[11px] font-bold tracking-wide px-2 py-0.5 rounded-md border shrink-0 transition-colors shadow-sm ${theme.badge}`}>
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
                <div className={`flex flex-col ml-3 mt-1 relative border-l-2 ${theme.borderLeft} rounded-bl-xl pl-1 bg-gradient-to-br from-black/20 to-transparent`}>
                    {node.children.map((child, idx) => (
                        <TreeNode key={`${child.name}-${idx}`} node={child} depth={depth + 1} forceExpand={forceExpand} />
                    ))}
                </div>
            )}
        </div>
    );
};

export const ModelExplorer: React.FC<ModelExplorerProps> = ({ modelInfo }) => {
    // null = natural state, true = all expanded, false = all collapsed
    const [forceExpand, setForceExpand] = useState<boolean | null>(null);
    const [allExpanded, setAllExpanded] = useState(false);

    const handleExpandAll = () => {
        setAllExpanded(true);
        setForceExpand(true);
        // Reset to null after a tick so individual toggles work again
        setTimeout(() => setForceExpand(null), 50);
    };

    const handleCollapseAll = () => {
        setAllExpanded(false);
        setForceExpand(false);
        setTimeout(() => setForceExpand(null), 50);
    };

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
                    {/* Expand / Collapse All buttons */}
                    <div className="flex items-center gap-1 bg-slate-800/60 p-1 rounded-xl border border-slate-700/50">
                        <button
                            onClick={handleExpandAll}
                            title="Expand All"
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200
                                ${allExpanded
                                    ? 'bg-slate-700/80 text-white shadow-sm'
                                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/40'}`}
                        >
                            <ChevronsUpDown className="w-3.5 h-3.5" />
                            Expand All
                        </button>
                        <button
                            onClick={handleCollapseAll}
                            title="Collapse All"
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200
                                ${!allExpanded
                                    ? 'bg-slate-700/80 text-white shadow-sm'
                                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/40'}`}
                        >
                            <ChevronsDownUp className="w-3.5 h-3.5" />
                            Collapse All
                        </button>
                    </div>

                    <div className="h-8 w-px bg-slate-800" />

                    <div className="flex flex-col items-end">
                        <span className="text-xs text-slate-500 uppercase font-bold tracking-wider">Total Params</span>
                        <span className="text-lg font-semibold text-slate-200">{modelInfo.total_params}</span>
                    </div>
                    <div className="h-8 w-px bg-slate-800" />
                    <div className="flex flex-col items-end">
                        <span className="text-xs text-slate-500 uppercase font-bold tracking-wider">Trainable</span>
                        <span className="text-lg font-semibold text-emerald-400">{modelInfo.trainable_params}</span>
                    </div>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                {modelInfo.architecture ? (
                    <div className="bg-[#0b0f19] rounded-2xl p-4 border border-slate-800/50 shadow-inner">
                        <TreeNode node={modelInfo.architecture} depth={0} forceExpand={forceExpand} />
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
