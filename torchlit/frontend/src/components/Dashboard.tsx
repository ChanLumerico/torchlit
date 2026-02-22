import React, { useEffect, useState, useRef } from 'react';
import { Activity, ServerCrash, Zap, Monitor, HardDrive, Filter, Layers, X, ChevronDown } from 'lucide-react';
import { MetricChart } from './MetricChart';
import type { MetricLog, SysStats, ModelInfo } from '../types';

export const Dashboard: React.FC = () => {
    const [isConnected, setIsConnected] = useState<boolean>(false);
    const [experiments, setExperiments] = useState<string[]>([]);
    const [selectedExps, setSelectedExps] = useState<string[]>([]);

    // Data for all selected experiments: { "exp_name": [logs] }
    const [allMetrics, setAllMetrics] = useState<Record<string, any[]>>({});
    const [latestStats, setLatestStats] = useState<Record<string, SysStats>>({});
    const [modelInfos, setModelInfos] = useState<Record<string, ModelInfo>>({});

    const [lastUpdate, setLastUpdate] = useState<number>(0);
    const [isTraining, setIsTraining] = useState<boolean>(false);

    // Available metric keys
    const [metricKeys, setMetricKeys] = useState<string[]>([]);

    // UI states
    const [dropdownOpen, setDropdownOpen] = useState<boolean>(false);
    const [smoothing, setSmoothing] = useState<number>(0.6);
    const [zoomedChart, setZoomedChart] = useState<string | null>(null);

    const sockets = useRef<Map<string, WebSocket>>(new Map());

    const isDev = import.meta.env.DEV;
    const API_URL = isDev ? 'http://localhost:8000' : '';
    const WS_URL = isDev ? 'ws://localhost:8000' : (window.location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + window.location.host;

    // 1. Fetch available experiments on load
    useEffect(() => {
        fetch(`${API_URL}/api/experiments`)
            .then(res => res.json())
            .then(data => {
                if (data.experiments && data.experiments.length > 0) {
                    setExperiments(data.experiments);
                    if (selectedExps.length === 0) setSelectedExps([data.experiments[0]]);
                }
            })
            .catch(console.error);
    }, []);

    const handleDeleteExp = async (expToDelete: string, e: React.MouseEvent) => {
        e.stopPropagation();
        try {
            await fetch(`${API_URL}/api/experiments/${expToDelete}`, { method: 'DELETE' });
            const remaining = experiments.filter(exp => exp !== expToDelete);
            setExperiments(remaining);
            if (selectedExps.includes(expToDelete)) {
                setSelectedExps(prev => prev.filter(e => e !== expToDelete));
            }
        } catch (err) {
            console.error("Failed to delete experiment", err);
        }
    };

    const handleClearAll = async () => {
        if (!confirm("Are you sure you want to clear ALL training sessions? This cannot be undone.")) {
            return;
        }
        try {
            const response = await fetch(`${API_URL}/api/experiments/clear`, { method: 'POST' });
            if (response.ok) {
                setExperiments([]);
                setSelectedExps([]);
                setAllMetrics({});
                setLatestStats({});
                setModelInfos({});
                setDropdownOpen(false);
            }
        } catch (err) {
            console.error("Failed to clear experiments:", err);
        }
    };

    // 2. Manage multiple WebSocket connections
    useEffect(() => {
        // Clean up sockets that are no longer selected
        sockets.current.forEach((socket, exp) => {
            if (!selectedExps.includes(exp)) {
                socket.close();
                sockets.current.delete(exp);
                // Clear data for unselected
                setAllMetrics(prev => {
                    const next = { ...prev };
                    delete next[exp];
                    return next;
                });
            }
        });

        if (selectedExps.length === 0) {
            setIsConnected(false);
            return;
        }

        selectedExps.forEach(exp => {
            if (!sockets.current.has(exp)) {
                const socket = new WebSocket(`${WS_URL}/ws/stream/${exp}`);

                socket.onopen = () => setIsConnected(true);
                socket.onclose = () => {
                    // Check if any sockets are still connected
                    const anyConnected = Array.from(sockets.current.values()).some(s => s.readyState === WebSocket.OPEN);
                    setIsConnected(anyConnected);
                };
                socket.onerror = () => setIsConnected(false);

                socket.onmessage = (event) => {
                    const data: MetricLog = JSON.parse(event.data);
                    setLastUpdate(Date.now());

                    const flatData = {
                        step: data.step,
                        ...data.metrics
                    };

                    setAllMetrics(prev => {
                        const currentExpData = prev[exp] || [];
                        const next = [...currentExpData, flatData];
                        const windowed = next.length > 1000 ? next.slice(next.length - 1000) : next;
                        return { ...prev, [exp]: windowed };
                    });

                    // Extract and merge keys
                    setMetricKeys(prev => {
                        const newKeys = Object.keys(data.metrics);
                        const merged = new Set([...prev, ...newKeys]);
                        return Array.from(merged);
                    });

                    if (data.model_info) {
                        setModelInfos(prev => ({ ...prev, [exp]: data.model_info! }));
                    }
                };

                sockets.current.set(exp, socket);
            }
        });

        return () => {
            // No global cleanup here to maintain other sockets, 
            // the per-exp cleanup handles it.
        };
    }, [selectedExps]);

    // Cleanup all on unmount
    useEffect(() => {
        return () => {
            sockets.current.forEach(s => s.close());
            sockets.current.clear();
        };
    }, []);

    // 3. Merged Data for Charts
    const mergedData = React.useMemo(() => {
        const steps = new Set<number>();
        Object.values(allMetrics).forEach(data => {
            data.forEach(d => steps.add(d.step));
        });

        const sortedSteps = Array.from(steps).sort((a, b) => a - b);

        return sortedSteps.map(step => {
            const entry: any = { step };
            selectedExps.forEach(exp => {
                const expData = allMetrics[exp] || [];
                const stepData = expData.find(d => d.step === step);
                if (stepData) {
                    Object.keys(stepData).forEach(key => {
                        if (key !== 'step') {
                            entry[`${key}::${exp}`] = stepData[key];
                        }
                    });
                }
            });
            return entry;
        });
    }, [allMetrics, selectedExps]);

    // Check training status
    useEffect(() => {
        let timeout: number | undefined;
        if (lastUpdate > 0 && isConnected) {
            setIsTraining(true);
            timeout = window.setTimeout(() => setIsTraining(false), 3000);
        } else {
            setIsTraining(false);
        }
        return () => {
            if (timeout) window.clearTimeout(timeout);
        };
    }, [lastUpdate, isConnected]);

    return (
        <div className="min-h-screen bg-[#0b0f19] text-slate-200 font-sans selection:bg-brand selection:text-white">

            {/* Top Navbar */}
            <nav className="sticky top-0 z-50 backdrop-blur-md bg-[#0b0f19]/80 border-b border-slate-800/80 px-8 py-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="bg-brand/20 p-2 rounded-xl">
                        <Zap className="text-brand w-6 h-6" />
                    </div>
                    <h1 className="text-2xl font-bold bg-gradient-to-r from-brand to-purple-400 bg-clip-text text-transparent">
                        torchlit
                    </h1>
                </div>

                <div className="flex items-center gap-6">
                    {/* Smoothing Slider */}
                    <div className="flex items-center gap-3 bg-slate-800/50 px-4 py-2 rounded-full border border-slate-700/50">
                        <span className="text-xs font-bold text-slate-500 uppercase tracking-tighter">Smooth</span>
                        <input
                            type="range"
                            min="0"
                            max="0.99"
                            step="0.01"
                            value={smoothing}
                            onChange={(e) => setSmoothing(parseFloat(e.target.value))}
                            className="w-24 h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-brand"
                        />
                        <span className="text-xs font-mono text-brand w-8">{smoothing.toFixed(2)}</span>
                    </div>

                    <div className="relative">
                        <div
                            className="flex items-center gap-2 text-sm text-slate-400 bg-slate-800/50 px-4 py-2 rounded-full border border-slate-700/50 cursor-pointer hover:bg-slate-800 transition-colors"
                            onClick={() => setDropdownOpen(!dropdownOpen)}
                        >
                            <Filter className="w-4 h-4" />
                            <span className="font-medium text-slate-200 select-none">
                                {selectedExps.length === 0 ? "No Session" :
                                    selectedExps.length === 1 ? selectedExps[0] :
                                        `${selectedExps.length} Sessions Compared`}
                            </span>
                            <ChevronDown className="w-4 h-4 ml-2" />
                        </div>

                        {dropdownOpen && (
                            <div className="absolute top-full mt-2 w-72 bg-slate-800 border border-slate-700 rounded-2xl shadow-xl overflow-hidden z-50 right-0">
                                {experiments.length === 0 ? (
                                    <div className="px-4 py-3 text-sm text-slate-400">No experiments available</div>
                                ) : (
                                    experiments.map(exp => {
                                        const isSelected = selectedExps.includes(exp);
                                        return (
                                            <div
                                                key={exp}
                                                className={`flex items-center justify-between px-4 py-3 hover:bg-slate-700/50 cursor-pointer transition-colors ${isSelected ? 'bg-brand/10 border-l-2 border-brand' : ''}`}
                                                onClick={() => {
                                                    if (isSelected) {
                                                        setSelectedExps(prev => prev.filter(e => e !== exp));
                                                    } else {
                                                        setSelectedExps(prev => [...prev, exp]);
                                                    }
                                                }}
                                            >
                                                <div className="flex items-center gap-3">
                                                    <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${isSelected ? 'bg-brand border-brand' : 'border-slate-600'}`}>
                                                        {isSelected && <Activity size={10} className="text-white" />}
                                                    </div>
                                                    <span className={`text-sm font-medium ${isSelected ? 'text-brand' : 'text-slate-200'}`}>{exp}</span>
                                                </div>
                                                <button
                                                    onClick={(e) => handleDeleteExp(exp, e)}
                                                    className="p-1 rounded-full text-slate-400 hover:bg-slate-600 hover:text-red-400 transition-colors"
                                                    title="Delete Session"
                                                >
                                                    <X className="w-4 h-4" />
                                                </button>
                                            </div>
                                        );
                                    })
                                )}
                                {experiments.length > 0 && (
                                    <div
                                        className="border-t border-slate-700 bg-slate-900/50 hover:bg-red-500/10 transition-colors px-4 py-3 flex items-center gap-2 text-red-400 text-xs font-bold uppercase tracking-wider cursor-pointer select-none"
                                        onClick={handleClearAll}
                                    >
                                        <X className="w-4 h-4" />
                                        Clear All Sessions
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    <div className={`flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-full border ${isConnected ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'}`}>
                        {isConnected ? <Activity className="w-4 h-4 animate-pulse" /> : <ServerCrash className="w-4 h-4" />}
                        {isConnected ? 'Live Logging' : 'Disconnected'}
                    </div>
                </div>
            </nav>

            {/* Main Content */}
            <main className="max-w-7xl mx-auto px-8 py-8 space-y-8">

                {/* Model Summary Banner (Primary selected session) */}
                {selectedExps.length > 0 && modelInfos[selectedExps[0]] && (
                    <div className="bg-gradient-to-r from-brand/10 to-transparent border border-brand/20 p-6 rounded-3xl mb-8">
                        <div className="flex items-center gap-4 mb-4">
                            <div className="bg-brand/20 p-3 rounded-2xl">
                                <Layers className="text-brand w-6 h-6" />
                            </div>
                            <div className="flex-1">
                                <h3 className="text-xl font-bold text-slate-100">{modelInfos[selectedExps[0]].name || 'PyTorch Model'}</h3>
                                <p className="text-brand text-sm font-medium">Model Architecture Overview ({selectedExps[0]})</p>
                            </div>
                            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold uppercase tracking-wider border shadow-sm ${isTraining ? 'bg-brand/10 text-brand border-brand/20' : 'bg-slate-800/50 text-slate-500 border-slate-700/50'}`}>
                                <span className={`w-2 h-2 rounded-full ${isTraining ? 'bg-brand animate-pulse' : 'bg-slate-600'}`}></span>
                                {isTraining ? 'Training Active' : 'Stopped'}
                            </div>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            {modelInfos[selectedExps[0]].total_params && (
                                <div className="bg-slate-900/50 p-4 rounded-2xl border border-slate-700/50">
                                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Total Params</p>
                                    <p className="text-lg font-semibold text-slate-200">{modelInfos[selectedExps[0]].total_params}</p>
                                </div>
                            )}
                            {modelInfos[selectedExps[0]].trainable_params && (
                                <div className="bg-slate-900/50 p-4 rounded-2xl border border-slate-700/50">
                                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Trainable Params</p>
                                    <p className="text-lg font-semibold text-slate-200">{modelInfos[selectedExps[0]].trainable_params}</p>
                                </div>
                            )}
                            {modelInfos[selectedExps[0]].activation_size && (
                                <div className="bg-slate-900/50 p-4 rounded-2xl border border-slate-700/50">
                                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Activation Size</p>
                                    <p className="text-lg font-semibold text-slate-200">{modelInfos[selectedExps[0]].activation_size}</p>
                                </div>
                            )}
                            {Object.entries(modelInfos[selectedExps[0]])
                                .filter(([key]) => !['name', 'total_params', 'trainable_params', 'activation_size'].includes(key))
                                .map(([key, value]) => (
                                    <div key={key} className="bg-slate-900/50 p-4 rounded-2xl border border-slate-700/50">
                                        <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">{key.replace(/_/g, ' ')}</p>
                                        <p className="text-lg font-semibold text-slate-200">{String(value)}</p>
                                    </div>
                                ))}
                        </div>
                    </div>
                )}

                {/* System Stats Header (Primary) */}
                {selectedExps.length > 0 && latestStats[selectedExps[0]] && (() => {
                    const primaryStats = latestStats[selectedExps[0]];
                    return (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="bg-gradient-to-br from-slate-800/80 to-slate-800/40 backdrop-blur-md border border-slate-700/50 p-6 rounded-3xl flex items-center justify-between shadow-lg">
                                <div>
                                    <p className="text-slate-400 text-sm font-medium uppercase tracking-wider mb-1">Compute Usage</p>
                                    <h2 className="text-4xl font-light text-slate-100">
                                        {primaryStats.cpu_percent.toFixed(1)}%
                                    </h2>
                                    <p className="text-slate-500 text-xs mt-2 uppercase flex items-center gap-1">
                                        Primary: <span className="text-brand font-semibold">{selectedExps[0]}</span>
                                    </p>
                                </div>
                                <div className="bg-blue-500/20 p-4 rounded-2xl">
                                    <Monitor className="text-blue-400 w-8 h-8" />
                                </div>
                            </div>

                            <div className="bg-gradient-to-br from-slate-800/80 to-slate-800/40 backdrop-blur-md border border-slate-700/50 p-6 rounded-3xl flex items-center justify-between shadow-lg">
                                <div>
                                    <p className="text-slate-400 text-sm font-medium uppercase tracking-wider mb-1">
                                        {primaryStats.device_type !== 'cpu' ? 'VRAM Usage' : 'RAM Usage'}
                                    </p>
                                    <h2 className="text-4xl font-light text-slate-100">
                                        {primaryStats.vram_percent != null
                                            ? primaryStats.vram_percent.toFixed(1)
                                            : (primaryStats.ram_percent?.toFixed(1) || '--')}%
                                    </h2>
                                    <p className="text-slate-500 text-xs mt-2 uppercase">
                                        Device: <span className="text-emerald-400 font-semibold">{primaryStats.device_name || 'CPU'}</span>
                                    </p>
                                </div>
                                <div className="bg-emerald-500/20 p-4 rounded-2xl">
                                    <HardDrive className="text-emerald-400 w-8 h-8" />
                                </div>
                            </div>
                        </div>
                    );
                })()}

                {/* Charts Grid */}
                {mergedData.length > 0 ? (
                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                        {metricKeys.map((key) => (
                            <MetricChart
                                key={key}
                                title={key}
                                data={mergedData}
                                selectedExps={selectedExps}
                                metricKey={key}
                                smoothing={smoothing}
                                onZoom={() => setZoomedChart(key)}
                            />
                        ))}
                    </div>
                ) : (
                    <div className="h-96 flex flex-col items-center justify-center text-slate-500 bg-slate-800/20 border border-slate-800 rounded-3xl border-dashed">
                        <Activity className="w-12 h-12 mb-4 opacity-50" />
                        <p className="text-lg font-medium">Waiting for training data...</p>
                        <p className="text-sm">Start your PyTorch loop with the torchlit Monitor.</p>
                    </div>
                )}

            </main>

            {/* Zoom Modal */}
            {zoomedChart && (
                <div
                    className="fixed inset-0 z-[100] flex items-center justify-center p-8 backdrop-blur-xl bg-black/60"
                    onClick={() => setZoomedChart(null)}
                >
                    <div
                        className="relative w-full max-w-6xl h-[80vh] animate-in zoom-in-95 duration-200"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <button
                            onClick={() => setZoomedChart(null)}
                            className="absolute -top-12 right-0 p-2 text-slate-400 hover:text-white transition-colors flex items-center gap-2 font-medium"
                        >
                            <span>Close</span>
                            <X size={24} />
                        </button>

                        <MetricChart
                            title={zoomedChart}
                            data={mergedData}
                            selectedExps={selectedExps}
                            metricKey={zoomedChart}
                            smoothing={smoothing}
                            isZoomed={true}
                        />
                    </div>
                </div>
            )}
        </div>
    );
};
