export interface SysStats {
    cpu_percent: number;
    ram_percent: number;
    device_type?: string;     // 'cpu', 'cuda', 'mps'
    device_name?: string;     // e.g. 'NVIDIA GeForce RTX 3090'
    vram_percent?: number | null;
}

export interface ModelInfo {
    name?: string;
    total_params?: string | number;
    trainable_params?: string | number;
    activation_size?: string;
    [key: string]: any;
}

export interface MetricLog {
    exp_name: string;
    step: number;
    metrics: Record<string, number>;
    sys_stats: SysStats;
    model_info?: ModelInfo;
}
