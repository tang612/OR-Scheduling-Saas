import type { Solution, Task } from './types'

const STATUS_TEXT: Record<string, string> = {
  OPTIMAL: '最优解',
  FEASIBLE: '可行解',
  INFEASIBLE: '不可行',
  UNKNOWN: '未知',
}

const TERMINATION_TEXT: Record<string, string> = {
  optimal: '达到最优',
  time_limit: '达到时间上限',
  cancelled: '用户取消',
  infeasible: '不可行',
  unknown: '未知',
}

const PARAM_LABEL: Record<string, string> = {
  engine: '求解引擎',
  time_limit_s: '时间上限（秒）',
  num_workers: '并行线程数',
  log_search_progress: '搜索过程日志',
  weights: '目标权重 λ (makespan, ΣT, ΣC)',
  seed: '随机种子',
  solver_request: '求解器请求',
}

/** 参数详情：任务基础信息 + 求解参数回显 + 求解状态 */
export default function ParamsPanel({ task, solution }: { task: Task; solution?: Solution }) {
  const fmt = (v: string | undefined) => (v ? new Date(v).toLocaleString() : '-')
  const params = solution?.params || {}

  const rows: [string, string][] = [
    ['任务名称', task.name],
    ['任务 ID', task.id],
    ['提交时间', fmt(task.created_at)],
    ['调度时间', fmt(task.dispatched_at)],
    ['完成时间', fmt(task.finished_at)],
  ]
  if (task.finished_at && task.dispatched_at) {
    const total = (new Date(task.finished_at).getTime() - new Date(task.created_at).getTime()) / 1000
    rows.push(['总耗时', total.toFixed(1) + 's'])
  }

  return (
    <div className="params-panel">
      <h5>任务基础信息</h5>
      <table className="kv">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}><td className="kv-k">{k}</td><td>{v}</td></tr>
          ))}
        </tbody>
      </table>

      {solution && (
        <>
          <h5>求解状态</h5>
          <table className="kv">
            <tbody>
              <tr><td className="kv-k">求解引擎</td><td>{solution.engine}</td></tr>
              <tr><td className="kv-k">解状态</td><td>{STATUS_TEXT[solution.status] || solution.status}</td></tr>
              <tr><td className="kv-k">终止原因</td><td>{TERMINATION_TEXT[solution.termination || ''] || solution.termination || '-'}</td></tr>
              <tr><td className="kv-k">最优性 Gap</td><td>{solution.gap != null ? (solution.gap * 100).toFixed(2) + '%' : '-'}</td></tr>
              <tr><td className="kv-k">求解耗时</td><td>{solution.solve_time_s.toFixed(2)}s</td></tr>
              {solution.iterations != null && <tr><td className="kv-k">迭代轮次</td><td>{solution.iterations}</td></tr>}
            </tbody>
          </table>

          {Object.keys(params).length > 0 && (
            <>
              <h5>求解参数回显</h5>
              <table className="kv">
                <tbody>
                  {Object.entries(params).map(([k, v]) => (
                    <tr key={k}>
                      <td className="kv-k">{PARAM_LABEL[k] || k}</td>
                      <td>{Array.isArray(v) ? v.join(', ') : String(v)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}
    </div>
  )
}
