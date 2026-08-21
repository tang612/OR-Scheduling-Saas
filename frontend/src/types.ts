// Dashboard v2 共享类型

export interface TimelineItem {
  status: string
  stage: string
  at: string
}

export interface Objective {
  makespan?: number
  tardiness?: number
  completion?: number
  total?: number
}

export interface Task {
  id: string
  name: string
  status: string
  progress: number
  stage: string
  solver?: string
  objective?: Objective
  dataset_id: string
  created_at: string
  dispatched_at?: string
  finished_at?: string
  queue_position?: number | null
  queue_timeout?: boolean
  timeline?: TimelineItem[]
}

export interface OperatorStat {
  name: string
  uses: number
  improvements: number
  hit_rate: number
}

export interface IterLogItem {
  iter: number
  objective: number
  op: string
  improved: boolean
}

export interface ConvergencePoint {
  iter?: number
  t?: number
  objective?: number
  bound?: number
}

export interface Solution {
  id: string
  task_id: string
  engine: string
  status: string
  objective: Objective
  gap?: number
  solve_time_s: number
  created_at: string
  initial_objective?: Objective | null
  convergence?: ConvergencePoint[]
  iterations?: number | null
  operator_stats?: OperatorStat[]
  iteration_log?: IterLogItem[]
  termination?: string | null
  params?: Record<string, unknown> | null
  logs?: string[]
}

export interface GanttData {
  machines: any[]
  jobs: any[]
  setup: any[]
  meta: any
}

export interface SSEEvent {
  type: 'snapshot' | 'status' | 'progress' | 'log' | 'done' | 'failed' | 'cancelled'
  status?: string
  stage?: string
  progress?: number
  at?: string
  timeline?: TimelineItem[]
  dispatched_at?: string
  queue_timeout?: boolean
  lines?: string[]
  solution_ids?: string[]
  error?: { code: string; msg: string }
}

export type TabKey = 'log' | 'analysis' | 'params'
