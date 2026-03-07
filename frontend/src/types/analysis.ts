export interface MetricComparison {
  metric: string
  mean_a: number
  std_a: number
  mean_b: number
  std_b: number
  u_statistic: number
  p_value: number
  significant: boolean
  effect_size: number
}

export interface CompareResult {
  label_a: string
  label_b: string
  num_iterations: number
  metrics: MetricComparison[]
  raw_a: Record<string, number[]>
  raw_b: Record<string, number[]>
}

export interface MetricStat {
  metric: string
  mean: number
  std: number
  min: number
  max: number
  values: number[]
}

export interface SweepPoint {
  parameter_value: number
  metric_results: MetricStat[]
}

export interface SweepResult {
  parameter_name: string
  points: SweepPoint[]
}
