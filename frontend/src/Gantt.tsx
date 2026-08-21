import { useMemo, useState } from 'react'
import type { WheelEvent as ReactWheelEvent } from 'react'

interface GanttBlock {
  id: string
  machine: string
  start: number
  end: number
  recipe?: string
  tardy?: boolean
  type?: string
}

interface GanttData {
  machines: { id: string; name: string }[]
  jobs: GanttBlock[]
  setup: GanttBlock[]
  meta: {
    makespan?: number
    tardiness?: number
    completion?: number
    solver?: string
    gap?: number
  }
}

const COLORS = ['#4a6cf7', '#e67e22', '#27ae60', '#9b59b6', '#e74c3c', '#16a085', '#f39c12', '#2980b9']
const PX_PER_UNIT = 4

export default function Gantt({ data }: { data: GanttData }) {
  const [scale, setScale] = useState(1)
  const [hover, setHover] = useState<{ x: number; y: number; block: GanttBlock; machine: string } | null>(null)

  const maxTime = Math.max(data.meta.makespan || 1, 1)

  // 平均资源利用率 = 机器占用时间(加工+切换) / (机器数 × makespan)
  const utilization = useMemo(() => {
    const busy =
      data.jobs.reduce((s, j) => s + (j.end - j.start), 0) +
      data.setup.reduce((s, s2) => s + (s2.end - s2.start), 0)
    const available = data.machines.length * maxTime
    return available > 0 ? busy / available : 0
  }, [data, maxTime])

  const trackWidth = maxTime * PX_PER_UNIT * scale

  const onWheel = (e: ReactWheelEvent) => {
    e.preventDefault()
    setScale((s) => Math.min(8, Math.max(0.5, s + (e.deltaY < 0 ? 0.2 : -0.2))))
  }

  const colorMap: Record<string, string> = {}
  let ci = 0
  for (const j of data.jobs) {
    if (j.recipe && !colorMap[j.recipe]) colorMap[j.recipe] = COLORS[ci++ % COLORS.length]
  }

  return (
    <div>
      {/* 核心指标看板 */}
      <div className="kpi-board">
        <div className="kpi-item">
          <div className="kpi-value hl">{data.meta.makespan ?? '-'}</div>
          <div className="kpi-label">总工期 makespan</div>
        </div>
        <div className="kpi-item">
          <div className="kpi-value">{data.meta.tardiness ?? '-'}</div>
          <div className="kpi-label">总延误 ΣT</div>
        </div>
        <div className="kpi-item">
          <div className="kpi-value">{data.meta.completion ?? '-'}</div>
          <div className="kpi-label">总完工 ΣC</div>
        </div>
        <div className="kpi-item">
          <div className="kpi-value">{(utilization * 100).toFixed(1)}%</div>
          <div className="kpi-label">平均资源利用率</div>
        </div>
      </div>

      <div className="toolbar">
        <span className="hint">滚轮缩放时间轴 · 悬停查看详情 · 当前 {scale.toFixed(1)}×</span>
        <button className="btn secondary small" onClick={() => setScale(1)}>重置缩放</button>
      </div>

      <div className="gantt-wrap">
        <div className="gantt" onWheel={onWheel}>
          {data.machines.map((m) => {
            const jobs = data.jobs.filter((j) => j.machine === m.id)
            const setups = data.setup.filter((s) => s.machine === m.id)
            return (
              <div className="gantt-row" key={m.id}>
                <div className="gantt-label">{m.name}</div>
                <div className="gantt-track" style={{ width: trackWidth }}>
                  {setups.map((s) => (
                    <div
                      key={s.id}
                      className="gantt-block gantt-setup"
                      style={{
                        left: s.start * PX_PER_UNIT * scale,
                        width: Math.max((s.end - s.start) * PX_PER_UNIT * scale, 1),
                      }}
                      onMouseEnter={(e) => setHover({ x: e.clientX, y: e.clientY, block: s, machine: m.name })}
                      onMouseLeave={() => setHover(null)}
                    />
                  ))}
                  {jobs.map((j) => (
                    <div
                      key={j.id}
                      className={`gantt-block ${j.tardy ? 'tardy' : ''}`}
                      style={{
                        left: j.start * PX_PER_UNIT * scale,
                        width: Math.max((j.end - j.start) * PX_PER_UNIT * scale, 2),
                        background: colorMap[j.recipe || ''] || '#888',
                      }}
                      onMouseEnter={(e) => setHover({ x: e.clientX, y: e.clientY, block: j, machine: m.name })}
                      onMouseLeave={() => setHover(null)}
                    >
                      {j.id}
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {hover && (
        <div className="gantt-tooltip" style={{ left: hover.x + 12, top: hover.y + 12 }}>
          <div className="tt-title">{hover.block.recipe ? hover.block.id : '切换段'}</div>
          <div>机器：{hover.machine}</div>
          {hover.block.recipe && <div>配方：{hover.block.recipe}</div>}
          <div>时间：{hover.block.start} → {hover.block.end}（耗时 {hover.block.end - hover.block.start}）</div>
          {hover.block.tardy && <div className="tt-tardy">⚠ 拖期</div>}
        </div>
      )}
    </div>
  )
}
