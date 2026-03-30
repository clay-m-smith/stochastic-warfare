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

export interface DoctrineSchoolResult {
  school_id: string
  display_name: string
  win_rate: number
  mean_blue_destroyed: number
  mean_red_destroyed: number
  mean_duration_ticks: number
  std_blue_destroyed: number
  std_red_destroyed: number
  std_duration_ticks: number
}

export interface DoctrineCompareResult {
  scenario: string
  side_to_vary: string
  num_iterations: number
  results: DoctrineSchoolResult[]
}
