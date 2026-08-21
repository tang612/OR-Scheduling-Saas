import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Solution } from './types'

const TERMINATION_TEXT: Record<string, string> = {
  optimal: '达到最优（OPTIMAL）',
  time_limit: '达到时间上限',
  cancelled: '用户取消',
  infeasible: '不可行',
  unknown: '未知',
}

const OP_TEXT: Record<string, string> = {
  random: '随机破坏：随机移除 k 个订单（k 随剩余时间递减）',
  worst: '最坏破坏：优先移除延误最大的订单',
}

export default function AnalysisPanel({ solution }: { solution?: Solution }) {
  if (!solution) return <div className="empty">暂无求解结果</div>
  return solution.engine.includes('ALNS') || solution.engine.includes('启发')
    ? <HeuristicView s={solution} />
    : <ExactView s={solution} />
}

/** 启发式专属：初始/最终目标、优化幅度、收敛曲线、算子贡献、迭代日志 */
function HeuristicView({ s }: { s: Solution }) {
  const init = s.initial_objective?.total
  const final = s.objective?.total
  const improvePct = useMemo(() => {
    if (init == null || final == null || !init) return null
    return ((init - final) / init) * 100
  }, [init, final])
  const conv = useMemo(() => (s.convergence || []).map((p) => ({ iter: p.iter, objective: p.objective })), [s.convergence])
  const [showAllLog, setShowAllLog] = useState(false)
  const iterLog = s.iteration_log || []
  const visibleLog = showAllLog ? iterLog : iterLog.slice(0, 100)

  return (
    <div className="analysis">
      <div className="kpi-board">
        <div className="kpi-item"><div className="kpi-value">{init ?? '-'}</div><div className="kpi-label">初始解目标值</div></div>
        <div className="kpi-item"><div className="kpi-value hl">{final ?? '-'}</div><div className="kpi-label">最终解目标值</div></div>
        <div className="kpi-item"><div className="kpi-value">{improvePct != null ? improvePct.toFixed(1) + '%' : '-'}</div><div className="kpi-label">优化幅度</div></div>
        <div className="kpi-item"><div className="kpi-value">{s.iterations ?? '-'}</div><div className="kpi-label">迭代轮次</div></div>
        <div className="kpi-item"><div className="kpi-value">{(s.solve_time_s ?? 0).toFixed(1)}s</div><div className="kpi-label">求解耗时</div></div>
      </div>

      <h5>Gap 收敛过程（目标值随迭代下降）</h5>
      {conv.length >= 2 ? (
        <div className="chart-box">
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={conv} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eef0f5" />
              <XAxis dataKey="iter" type="number" tick={{ fontSize: 11 }} label={{ value: '迭代轮次', position: 'insideBottom', offset: -4, fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} domain={['auto', 'auto']} width={64} />
              <Tooltip formatter={(v) => [v == null ? '-' : Number(v).toLocaleString(), '目标值']} />
              <Line type="monotone" dataKey="objective" stroke="#4a6cf7" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : <div className="empty-mini">收敛数据不足（迭代过少或已取消）</div>}

      {s.operator_stats && s.operator_stats.length > 0 && (
        <>
          <h5>优化方法与效果拆解</h5>
          <table>
            <thead><tr><th>优化方法</th><th>方法说明</th><th>被选次数</th><th>改进次数</th><th>改进命中率</th></tr></thead>
            <tbody>
              {s.operator_stats.map((o) => (
                <tr key={o.name}>
                  <td>{o.name === 'random' ? '随机破坏' : '最坏破坏'}</td>
                  <td className="op-desc">{OP_TEXT[o.name] || '-'}</td>
                  <td>{o.uses}</td>
                  <td>{o.improvements}</td>
                  <td>{(o.hit_rate * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {iterLog.length > 0 && (
        <>
          <h5>迭代日志（{iterLog.length} 条，改进事件高亮）</h5>
          <div className="iter-log">
            {visibleLog.map((l) => (
              <div key={l.iter} className={`iter-row ${l.improved ? 'improved' : ''}`}>
                <span className="iter-no">#{l.iter}</span>
                <span className="iter-obj">目标 {l.objective.toLocaleString()}</span>
                <span className="iter-op">{l.op === 'random' ? '随机破坏' : '最坏破坏'}</span>
                <span className="iter-badge">{l.improved ? '✓ 改进' : '—'}</span>
              </div>
            ))}
          </div>
          {!showAllLog && iterLog.length > 100 && (
            <button className="btn secondary small" onClick={() => setShowAllLog(true)}>显示全部 {iterLog.length} 条</button>
          )}
        </>
      )}

      <div className="result-note">
        本次求解采用 构造启发式 + ALNS 启发式算法，经过 {s.iterations ?? '-'} 轮迭代，
        将初始解{init != null && final != null ? `从 ${init.toLocaleString()} 优化到 ${final.toLocaleString()}（${improvePct != null ? improvePct.toFixed(1) : '-'}%）` : ''}，
        适用于大规模快速求解场景。
      </div>
    </div>
  )
}

/** 精确求解器专属：收敛轨迹（目标值 + 下界双线）、终止原因 */
function ExactView({ s }: { s: Solution }) {
  const conv = useMemo(() => (s.convergence || []).map((p) => ({ t: p.t, objective: p.objective, bound: p.bound })), [s.convergence])
  const first = conv[0]
  const last = conv[conv.length - 1]
  const gap = s.gap != null ? (s.gap * 100).toFixed(2) + '%' : '-'

  return (
    <div className="analysis">
      <div className="kpi-board">
        <div className="kpi-item"><div className="kpi-value hl">{s.objective?.total ?? '-'}</div><div className="kpi-label">最优目标值</div></div>
        <div className="kpi-item"><div className="kpi-value">{gap}</div><div className="kpi-label">最优性 Gap</div></div>
        <div className="kpi-item"><div className="kpi-value">{TERMINATION_TEXT[s.termination || ''] || s.termination || '-'}</div><div className="kpi-label">终止原因</div></div>
        <div className="kpi-item"><div className="kpi-value">{(s.solve_time_s ?? 0).toFixed(2)}s</div><div className="kpi-label">求解耗时</div></div>
      </div>

      <h5>求解收敛曲线（目标值 / 下界随时间变化）</h5>
      {conv.length >= 2 ? (
        <div className="chart-box">
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={conv} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eef0f5" />
              <XAxis dataKey="t" type="number" tick={{ fontSize: 11 }} label={{ value: '时间（秒）', position: 'insideBottom', offset: -4, fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} domain={['auto', 'auto']} width={64} />
              <Tooltip formatter={(v, name) => [v == null ? '-' : Number(v).toLocaleString(), name === 'objective' ? '目标值' : '下界']} />
              <Line type="monotone" dataKey="objective" name="objective" stroke="#4a6cf7" dot={false} strokeWidth={2} />
              <Line type="monotone" dataKey="bound" name="bound" stroke="#27ae60" dot={false} strokeWidth={1.5} strokeDasharray="4 2" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : <div className="empty-mini">收敛数据不足（秒级即达最优时轨迹点较少）</div>}

      {first && last && (
        <div className="milestones">
          <div className="milestone"><span className="ms-dot">1</span>首个可行解：t={first.t}s，目标 {first.objective?.toLocaleString()}</div>
          <div className="milestone"><span className="ms-dot">2</span>最终解：t={last.t}s，目标 {last.objective?.toLocaleString()}，下界 {last.bound?.toLocaleString()}</div>
          {s.termination === 'optimal' && <div className="milestone"><span className="ms-dot">✓</span>已证明最优（下界 = 目标值）</div>}
        </div>
      )}

      <div className="result-note">
        本次求解采用 CP-SAT 精确求解器（ORTools），终止原因：{TERMINATION_TEXT[s.termination || ''] || s.termination || '-'}。
        {s.status === 'OPTIMAL' ? '解已证明最优，可安全用于排程决策。' : '解为可行解（未证明最优），Gap 反映与下界的差距。'}
      </div>
    </div>
  )
}
