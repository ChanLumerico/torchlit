export interface SysStats {
    cpu_percent: number;
    ram_percent: number;
}

export interface MetricLog {
    exp_name: string;
    step: number;
    metrics: Record<string, number>;
    sys_stats: SysStats;
}
