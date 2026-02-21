import React, { useEffect, useState, useRef } from 'react';
import { Activity, ServerCrash, Zap, Monitor, HardDrive, Filter, Layers } from 'lucide-react';
import { MetricChart } from './MetricChart';
import type { MetricLog, SysStats, ModelInfo } from '../types';

export const Dashboard: React.FC = () => {
    const [isConnected, setIsConnected] = useState<boolean>(false);
    const [experiments, setExperiments] = useState<string[]>([]);
    const [activeExp, setActiveExp] = useState<string>('');

    // Data for the active experiment
    const [metricsData, setMetricsData] = useState<any[]>([]);
    const [latestStats, setLatestStats] = useState<SysStats | null>(null);
    const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null);

    // Available metric keys
    const [metricKeys, setMetricKeys] = useState<string[]>([]);

    const ws = useRef<WebSocket | null>(null);

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
                    if (!activeExp) setActiveExp(data.experiments[0]);
                }
            })
            .catch(console.error);
    }, []);

    // 2. Connect to WebSocket when active experiment changes
    useEffect(() => {
        if (!activeExp) return;

        // Reset Data
        setMetricsData([]);
        setMetricKeys([]);
        setLatestStats(null);
        setModelInfo(null);

        const connectWs = () => {
            const socket = new WebSocket(`${WS_URL}/ws/stream/${activeExp}`);

            socket.onopen = () => setIsConnected(true);
            socket.onclose = () => setIsConnected(false);
            socket.onerror = () => setIsConnected(false);

            socket.onmessage = (event) => {
                const data: MetricLog = JSON.parse(event.data);

                // Flatten payload for Recharts
                const flatData = {
                    step: data.step,
                    ...data.metrics
                };

                setMetricsData(prev => {
                    // Keep a rolling window of 1000 points to prevent frontend crash
                    const next = [...prev, flatData];
                    if (next.length > 1000) return next.slice(next.length - 1000);
                    return next;
                });

                // Extract Keys dynamically
                setMetricKeys(Object.keys(data.metrics));
                setLatestStats(data.sys_stats);
                if (data.model_info) setModelInfo(data.model_info);
            };

            ws.current = socket;
        };

        connectWs();

        return () => {
            if (ws.current) ws.current.close();
        };
    }, [activeExp]);

    // Colors for dynamic charts matching PyTorch orange aesthetics
    const colors = ["#EE4C2C", "#fb923c", "#fca5a5", "#fcd34d", "#f87171"];

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
                    <div className="flex items-center gap-2 text-sm text-slate-400 bg-slate-800/50 px-4 py-2 rounded-full border border-slate-700/50">
                        <Filter className="w-4 h-4" />
                        <select
                            value={activeExp}
                            onChange={(e) => setActiveExp(e.target.value)}
                            className="bg-transparent border-none outline-none appearance-none cursor-pointer font-medium text-slate-200"
                        >
                            {experiments.length === 0 && <option value="">No Active Training</option>}
                            {experiments.map(exp => (
                                <option key={exp} value={exp} className="bg-slate-800">{exp}</option>
                            ))}
                        </select>
                    </div>

                    <div className={`flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-full border ${isConnected ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'}`}>
                        {isConnected ? <Activity className="w-4 h-4 animate-pulse" /> : <ServerCrash className="w-4 h-4" />}
                        {isConnected ? 'Live Logging' : 'Disconnected'}
                    </div>
                </div>
            </nav>

            {/* Main Content */}
            <main className="max-w-7xl mx-auto px-8 py-8 space-y-8">

                {/* Model Summary Banner */}
                {modelInfo && (
                    <div className="bg-gradient-to-r from-brand/10 to-transparent border border-brand/20 p-6 rounded-3xl mb-8">
                        <div className="flex items-center gap-4 mb-4">
                            <div className="bg-brand/20 p-3 rounded-2xl">
                                <Layers className="text-brand w-6 h-6" />
                            </div>
                            <div>
                                <h3 className="text-xl font-bold text-slate-100">{modelInfo.name || 'PyTorch Model'}</h3>
                                <p className="text-brand text-sm font-medium">Model Architecture Overview</p>
                            </div>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            {modelInfo.total_params && (
                                <div className="bg-slate-900/50 p-4 rounded-2xl border border-slate-700/50">
                                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Total Params</p>
                                    <p className="text-lg font-semibold text-slate-200">{modelInfo.total_params}</p>
                                </div>
                            )}
                            {modelInfo.trainable_params && (
                                <div className="bg-slate-900/50 p-4 rounded-2xl border border-slate-700/50">
                                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Trainable Params</p>
                                    <p className="text-lg font-semibold text-slate-200">{modelInfo.trainable_params}</p>
                                </div>
                            )}
                            {modelInfo.activation_size && (
                                <div className="bg-slate-900/50 p-4 rounded-2xl border border-slate-700/50">
                                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Activation Size</p>
                                    <p className="text-lg font-semibold text-slate-200">{modelInfo.activation_size}</p>
                                </div>
                            )}
                            {Object.entries(modelInfo)
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

                {/* System Stats Header */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="bg-gradient-to-br from-slate-800/80 to-slate-800/40 backdrop-blur-md border border-slate-700/50 p-6 rounded-3xl flex items-center justify-between shadow-lg">
                        <div>
                            <p className="text-slate-400 text-sm font-medium uppercase tracking-wider mb-1">Compute Usage</p>
                            <h2 className="text-4xl font-light text-slate-100">
                                {latestStats?.cpu_percent.toFixed(1) || '--'}%
                            </h2>
                            <p className="text-slate-500 text-xs mt-2 uppercase flex items-center gap-1">
                                Device: <span className="text-brand font-semibold">{latestStats?.device_name || 'CPU'}</span>
                            </p>
                        </div>
                        <div className="bg-blue-500/20 p-4 rounded-2xl">
                            <Monitor className="text-blue-400 w-8 h-8" />
                        </div>
                    </div>

                    <div className="bg-gradient-to-br from-slate-800/80 to-slate-800/40 backdrop-blur-md border border-slate-700/50 p-6 rounded-3xl flex items-center justify-between shadow-lg">
                        <div>
                            <p className="text-slate-400 text-sm font-medium uppercase tracking-wider mb-1">
                                {latestStats?.device_type && latestStats.device_type !== 'cpu' ? 'VRAM Usage' : 'RAM Usage'}
                            </p>
                            <h2 className="text-4xl font-light text-slate-100">
                                {latestStats?.vram_percent != null
                                    ? latestStats.vram_percent.toFixed(1)
                                    : (latestStats?.ram_percent?.toFixed(1) || '--')}%
                            </h2>
                            <p className="text-slate-500 text-xs mt-2 uppercase">
                                {latestStats?.device_type && latestStats.device_type !== 'cpu' ? 'GPU Memory' : 'System Memory'}
                            </p>
                        </div>
                        <div className="bg-emerald-500/20 p-4 rounded-2xl">
                            <HardDrive className="text-emerald-400 w-8 h-8" />
                        </div>
                    </div>
                </div>

                {/* Charts Grid */}
                {metricsData.length > 0 ? (
                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                        {metricKeys.map((key, i) => (
                            <MetricChart
                                key={key}
                                title={key}
                                data={metricsData}
                                dataKey={key}
                                color={colors[i % colors.length]}
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
        </div>
    );
};
