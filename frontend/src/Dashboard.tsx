import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import Gantt from './Gantt'
import AnalysisPanel from './AnalysisPanel'
import LogPanel from './LogPanel'
import ParamsPanel from './ParamsPanel'
import type { GanttData, Solution, SSEEvent, TabKey, Task } from './types'

const TERMINAL = ['succeeded', 'failed', 'cancelled']

const STATUS_LABEL: Record<string, string> = {
  pending: '排队中',
  dispatched: '调度中',
  running: '求解中',
  succeeded: '求解成功',
  failed: '求解失败',
  cancelled: '已取消',
}

/** 任务结果 Dashboard v2：状态总览 + 左甘特图 / 右 Tab（日志·优化分析·参数） */
export default function Dashboard({
  task, onTaskUpdate, onBack, onTasksChanged,
}: {
  task: Task
  onTaskUpdate: (t: Task) => void
  onBack: () => void
  onTasksChanged: () => void
}) {
  const [solutions, setSolutions] = useState<Solution[]>([])
  const [gantt, setGantt] = useState<GanttData | null>(null)
  const [activeSol, setActiveSol] = useState('')
  const [logs, setLogs] = useState<string[]>([])
  const [tab, setTab] = useState<TabKey>(() => {
    const eng = task.solver || ''
    return eng.includes('ALNS') ? 'analysis' : 'log'
  })
  const [sseStatus, setSseStatus] = useState<'connected' | 'reconnecting' | 'polling'>('connected')
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [refreshHint, setRefreshHint] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const pollRef = useRef<number | null>(null)

  const isDone = TERMINAL.includes(task.status)
  const isHeur = (s: Solution) => s.engine.includes('ALNS') || s.engine.includes('启发')
  const activeSolution = solutions.find((s) => s.id === activeSol) || solutions[0]

  // ---- SSE 实时推送 + 断开轮询兜底 ----
  useEffect(() => {
    if (isDone) return
    esRef.current?.close()
    if (pollRef.current) { window.clearInterval(pollRef.current); pollRef.current = null }
    setSseStatus('connected')

    const es = new EventSource(`/api/v1/tasks/${task.id}/events`)
    esRef.current = es

    es.onmessage = (ev) => {
      let d: SSEEvent
      try { d = JSON.parse(ev.data) } catch { return }
      switch (d.type) {
        case 'snapshot':
          onTaskUpdate({
            ...task, status: d.status ?? task.status, progress: d.progress ?? task.progress,
            stage: d.stage ?? task.stage, timeline: d.timeline ?? task.timeline,
            dispatched_at: d.dispatched_at ?? task.dispatched_at,
            queue_timeout: d.queue_timeout ?? task.queue_timeout,
          })
          break
        case 'status':
          onTaskUpdate({
            ...task, status: d.status ?? task.status, stage: d.stage ?? task.stage,
            progress: d.progress != null ? d.progress : task.progress,
            timeline: [...(task.timeline || []), { status: d.status!, stage: d.stage!, at: d.at! }],
          })
          break
        case 'progress':
          onTaskUpdate({
            ...task, progress: d.progress ?? task.progress, stage: d.stage ?? task.stage,
          })
          break
        case 'log':
          setLogs((prev) => (prev.length > 20000 ? [...prev.slice(-10000), ...(d.lines || [])] : [...prev, ...(d.lines || [])]))
          break
        case 'done':
        case 'failed':
        case 'cancelled':
          refreshAfterFinish(d)
          es.close()
          break
        default:
          break  // 未知事件类型静默忽略（兼容旧 worker）
      }
    }

    es.onerror = () => {
      setSseStatus('reconnecting')
      // 断开 → 启动 10s 轮询兜底（EventSource 自动重连的同时保持状态更新）
      if (!pollRef.current) {
        pollRef.current = window.setInterval(() => {
          api('GET', `/tasks/${task.id}`).then((t: Task) => {
            onTaskUpdate(t)
            if (TERMINAL.includes(t.status)) {
              refreshAfterFinish(null)
              if (pollRef.current) { window.clearInterval(pollRef.current); pollRef.current = null }
            }
          }).catch(() => {})
        }, 10000)
        setSseStatus('polling')
      }
    }

    return () => {
      es.close()
      if (pollRef.current) { window.clearInterval(pollRef.current); pollRef.current = null }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task.id, isDone])

  const loadSolution = async (sid: string) => {
    try {
      const r = await api('GET', `/solutions/${sid}`)
      setGantt(r.gantt)
      setActiveSol(sid)
      // 全量日志补漏（SSE 断连期间可能丢失部分行）
      if (r.logs?.length && r.logs.length > 0) setLogs(r.logs)
      return r
    } catch (e: any) {
      setError(e.message)
      return null
    }
  }

  const refreshAfterFinish = async (d: SSEEvent | null) => {
    const t = await api('GET', `/tasks/${task.id}`).catch(() => null)
    if (t) onTaskUpdate(t)
    const sols = (await api('GET', `/tasks/${task.id}/solutions`).catch(() => [])) as Solution[]
    setSolutions(sols)
    if (sols.length > 0 && !activeSol) await loadSolution(sols[0].id)
    // 精确求解器：拉详情全量日志（补 SSE 实时推送遗漏；幂等——重复 GET 无害）
    for (const s of sols) {
      if (!isHeur(s)) {
        const r = await api('GET', `/solutions/${s.id}`).catch(() => null)
        if (r?.logs?.length) setLogs(r.logs)
      }
    }
    if (d?.type === 'failed') setError(`求解失败：${d.error?.msg || '未知错误'}`)
  }

  // ---- 方案/日志拉取兜底（修复：终态任务无 SSE 事件时可视化与日志不显示）----
  // ① 挂载/切换任务：总是拉一次现有方案（覆盖直接打开已完成任务 / 刷新详情页）
  useEffect(() => {
    refreshAfterFinish(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task.id])

  // ② 状态从未终态 → 终态：SSE done 事件已触发刷新，但「秒级完成任务」时
  //    snapshot 直接携带终态（无 done 事件可依赖），此处兜底补拉
  const prevStatusRef = useRef<string | null>(null)
  useEffect(() => {
    const prev = prevStatusRef.current
    prevStatusRef.current = task.status
    if (prev !== null && !TERMINAL.includes(prev) && TERMINAL.includes(task.status)) {
      refreshAfterFinish(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task.status])

  const cancelTask = async () => {
    if (!window.confirm('确认取消该任务？正在求解的任务将被终止。')) return
    setError(''); setInfo('')
    try {
      await api('DELETE', `/tasks/${task.id}`)
      setInfo('任务已取消')
      const t = await api('GET', `/tasks/${task.id}`)
      onTaskUpdate(t)
      onTasksChanged()
    } catch (e: any) { setError(e.message) }
  }

  const refreshStatus = async () => {
    try {
      setError(''); setInfo('')
      const t = await api('GET', `/tasks/${task.id}`)
      onTaskUpdate(t)
      setInfo('状态已刷新')
    } catch (e: any) { setError(e.message) }
  }

  // 排队超时 1 分钟确认提示（pending 超 60s 未变更）
  useEffect(() => {
    if (task.status !== 'pending') return
    const elapsed = (Date.now() - new Date(task.created_at).getTime()) / 1000
    if (elapsed > 60) setRefreshHint(true)
  }, [task.status, task.created_at])

  const pct = Math.round((task.progress || 0) * 100)

  return (
    <>
      {/* 顶部：状态总览 + 核心指标 + 快捷操作 */}
      <div className="card dash-top">
        <div className="row" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: 0, flex: 2 }}>任务详情：{task.name}</h3>
          <div className="btn-group">
            {!isDone && <button className="btn danger small" onClick={cancelTask}>取消任务</button>}
            <button className="btn secondary small" onClick={refreshStatus}>刷新状态</button>
            <button className="btn secondary small" onClick={onBack}>返回列表</button>
          </div>
        </div>

        {!isDone && sseStatus !== 'connected' && (
          <div className="sse-warn">
            {sseStatus === 'polling'
              ? '⚠ 实时推送已断开，已自动切换为定时刷新（10s/次）'
              : '连接中断，正在重连…'}
          </div>
        )}
        {refreshHint && task.status === 'pending' && (
          <div className="sse-warn warn-yellow">
            任务排队已超过 1 分钟，调度可能延迟，正在确认状态…（{task.queue_timeout ? '⚠ 已超排队阈值' : '仍在等待' }）
          </div>
        )}

        <div className="dash-overview">
          <span className={`badge ${task.status} ${task.queue_timeout ? 'badge-timeout' : ''}`}>
            {task.status === 'pending' && task.queue_timeout ? '排队超时' : STATUS_LABEL[task.status] || task.status}
          </span>
          <div className="progress-bar" style={{ flex: 3 }}>
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <span className="dash-pct">{pct}%</span>
          <span className="dash-stage">阶段：{task.stage || '-'}</span>
        </div>

        {/* 排队信息增强 */}
        {task.status === 'pending' && (
          <div className={`queue-info ${task.queue_timeout ? 'warn' : ''}`}>
            {task.queue_position != null
              ? <>您前面还有 <b>{task.queue_position}</b> 个任务等待执行 · 已排队 {Math.round((Date.now() - new Date(task.created_at).getTime()) / 1000)}s</>
              : <>已排队 {Math.round((Date.now() - new Date(task.created_at).getTime()) / 1000)}s，等待调度…</>}
          </div>
        )}

        {task.objective && (
          <div className="dash-obj">
            目标：makespan={task.objective.makespan ?? '-'} · ΣT={task.objective.tardiness ?? '-'} · ΣC={task.objective.completion ?? '-'}
          </div>
        )}

        {/* 状态时间线 */}
        {(task.timeline || []).length > 0 && (
          <div className="timeline">
            {(task.timeline || []).map((t, i) => (
              <div key={i} className="tl-item">
                <span className={`tl-dot ${t.status}`} />
                <span className="tl-status">{STATUS_LABEL[t.status] || t.status}</span>
                <span className="tl-stage">{t.stage}</span>
                <span className="tl-at">{new Date(t.at).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {error && <div className="error">{error}</div>}
      {info && <div className="success">{info}</div>}

      {/* 主体：左甘特图 / 右 Tab */}
      <div className="dash-body">
        <div className="dash-left card">
          <h4 style={{ marginTop: 0 }}>甘特图结果</h4>
          {solutions.length > 1 && (
            <div className="sol-tabs">
              {solutions.map((s) => (
                <button
                  key={s.id}
                  className={`sol-tab ${s.id === activeSol ? 'active' : ''}`}
                  onClick={() => loadSolution(s.id)}
                >
                  {s.engine} · {(s.objective.total ?? 0).toLocaleString()}
                </button>
              ))}
            </div>
          )}
          {gantt ? (
            <Gantt data={gantt} />
          ) : (
            <div className="empty">
              <span className="empty-icon">📊</span>
              {isDone ? '该任务无结果数据' : '求解完成后展示甘特图…'}
            </div>
          )}
        </div>

        <div className="dash-right card">
          <div className="tabs">
            <button className={`tab-btn ${tab === 'log' ? 'active' : ''}`} onClick={() => setTab('log')}>求解日志</button>
            <button className={`tab-btn ${tab === 'analysis' ? 'active' : ''}`} onClick={() => setTab('analysis')}>优化分析</button>
            <button className={`tab-btn ${tab === 'params' ? 'active' : ''}`} onClick={() => setTab('params')}>参数详情</button>
          </div>
          <div className="tab-body">
            {tab === 'log' && (
              <LogPanel
                taskId={task.id}
                logs={logs}
                engine={activeSolution?.engine}
                running={task.status === 'running' || task.status === 'dispatched'}
              />
            )}
            {tab === 'analysis' && <AnalysisPanel solution={activeSolution} />}
            {tab === 'params' && <ParamsPanel task={task} solution={activeSolution} />}
          </div>
        </div>
      </div>
    </>
  )
}
