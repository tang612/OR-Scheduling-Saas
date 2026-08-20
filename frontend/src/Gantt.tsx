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
  meta: { makespan?: number; tardiness?: number; solver?: string }
}

const COLORS = ['#4a6cf7', '#e67e22', '#27ae60', '#9b59b6', '#e74c3c', '#16a085', '#f39c12', '#2980b9']

export default function Gantt({ data }: { data: GanttData }) {
  const maxTime = Math.max(data.meta.makespan || 1, 1)
  const colorMap: Record<string, string> = {}
  let ci = 0
  for (const j of data.jobs) {
    if (j.recipe && !colorMap[j.recipe]) colorMap[j.recipe] = COLORS[ci++ % COLORS.length]
  }

  return (
    <div>
      <div style={{ fontSize: 12, color: '#888', marginBottom: 8 }}>
        总完工时间 makespan = {data.meta.makespan ?? '-'} · 总延误 ΣT = {data.meta.tardiness ?? '-'}
      </div>
      <div className="gantt">
        {data.machines.map((m) => {
          const jobs = data.jobs.filter((j) => j.machine === m.id)
          const setups = data.setup.filter((s) => s.machine === m.id)
          return (
            <div className="gantt-row" key={m.id}>
              <div className="gantt-label">{m.name}</div>
              <div className="gantt-track">
                {setups.map((s) => (
                  <div
                    key={s.id}
                    className="gantt-block gantt-setup"
                    style={{
                      left: `${(s.start / maxTime) * 100}%`,
                      width: `${((s.end - s.start) / maxTime) * 100}%`,
                    }}
                    title={`切换 ${s.start}→${s.end}`}
                  />
                ))}
                {jobs.map((j) => (
                  <div
                    key={j.id}
                    className={`gantt-block ${j.tardy ? 'tardy' : ''}`}
                    style={{
                      left: `${(j.start / maxTime) * 100}%`,
                      width: `${((j.end - j.start) / maxTime) * 100}%`,
                      background: colorMap[j.recipe || ''] || '#888',
                    }}
                    title={`${j.id} [${j.recipe}] ${j.start}→${j.end}`}
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
  )
}
