import { useCallback, useEffect, useRef, useState } from 'react'
import { api, setToken, getToken } from './api'
import Gantt from './Gantt'

interface Task {
  id: string
  name: string
  status: string
  progress: number
  stage: string
  solver?: string
  objective?: { makespan?: number; tardiness?: number; completion?: number; total?: number }
  dataset_id: string
  created_at: string
  finished_at?: string
}
interface Dataset { id: string; name: string; num_orders: number; num_machines: number; num_recipes: number }
interface Solution {
  id: string; task_id: string; engine: string; status: string
  objective: { makespan?: number; tardiness?: number; completion?: number; total?: number }
  gap?: number; solve_time_s: number
}
interface GanttData { machines: any[]; jobs: any[]; setup: any[]; meta: any }

export default function App() {
  const [authed, setAuthed] = useState(!!getToken())
  const [view, setView] = useState<'tasks' | 'submit' | 'detail'>('tasks')
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')

  // 登录
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  // 任务列表 / 数据集
  const [tasks, setTasks] = useState<Task[]>([])
  const [datasets, setDatasets] = useState<Dataset[]>([])

  // 提交表单
  const [taskName, setTaskName] = useState('')
  const [datasetId, setDatasetId] = useState('')
  const [lambda, setLambda] = useState('0,1,0')
  const [solver, setSolver] = useState('auto')
  const [timeBudget, setTimeBudget] = useState('')

  // 数据集上传
  const [dsName, setDsName] = useState('')
  const [dsJson, setDsJson] = useState('')

  // 详情
  const [currentTask, setCurrentTask] = useState<Task | null>(null)
  const [solutions, setSolutions] = useState<Solution[]>([])
  const [gantt, setGantt] = useState<GanttData | null>(null)
  const [activeSol, setActiveSol] = useState<string>('')
  const esRef = useRef<EventSource | null>(null)

  const loadTasks = useCallback(async () => {
    try { setTasks(await api('GET', '/tasks')) } catch (e: any) { setError(e.message) }
  }, [])

  const loadDatasets = useCallback(async () => {
    try { setDatasets(await api('GET', '/datasets')) } catch (e: any) { setError(e.message) }
  }, [])

  useEffect(() => { if (authed) { loadTasks(); loadDatasets() } }, [authed, loadTasks, loadDatasets])

  const doAuth = async () => {
    setError('')
    try {
      const path = mode === 'login' ? '/auth/login' : '/auth/register'
      const body = mode === 'login' ? { email, password } : { email, password, tenant_name: '默认租户' }
      const r = await api('POST', path, body)
      if (mode === 'register') { setMode('login'); setInfo('注册成功，请登录'); return }
      setToken(r.access_token)
      setAuthed(true)
      setView('tasks')
    } catch (e: any) { setError(e.message) }
  }

  const logout = () => { setToken(null); setAuthed(false); setView('tasks') }

  const uploadDataset = async () => {
    setError(''); setInfo('')
    try {
      const d = JSON.parse(dsJson)
      if (!d.machines || !d.orders || !d.recipes || !d.switch_matrix) throw new Error('JSON 需含 machines/orders/recipes/switch_matrix')
      const r = await api('POST', '/datasets', { name: dsName, ...d })
      setInfo(`数据集已上传（${r.num_orders} 单 × ${r.num_machines} 机）`)
      setDsName(''); setDsJson('')
      loadDatasets()
    } catch (e: any) { setError(e.message) }
  }

  const submitTask = async () => {
    setError(''); setInfo('')
    try {
      const ws = lambda.split(',').map(Number)
      if (ws.length !== 3) throw new Error('λ 权重需 3 个逗号分隔值，如 0,1,0')
      const cfg: any = { lambda: ws, solver }
      if (timeBudget) cfg.time_budget = Number(timeBudget)
      const r = await api('POST', '/tasks', { name: taskName, dataset_id: datasetId, config: cfg })
      setInfo(`任务已提交（${r.id}）`)
      setView('detail'); setCurrentTask(r); setSolutions([]); setGantt(null)
    } catch (e: any) { setError(e.message) }
  }

  const openTask = (t: Task) => {
    setView('detail'); setCurrentTask(t); setSolutions([]); setGantt(null); setActiveSol('')
  }

  const loadSolution = async (sid: string) => {
    try {
      const r = await api('GET', `/solutions/${sid}`)
      setGantt(r.gantt)
      setActiveSol(sid)
    } catch (e: any) { setError(e.message) }
  }

  // 详情页：SSE 实时进度 + 拉取方案
  useEffect(() => {
    if (view !== 'detail' || !currentTask) return
    if (currentTask.status === 'succeeded' || currentTask.status === 'failed' || currentTask.status === 'cancelled') {
      api('GET', `/tasks/${currentTask.id}/solutions`).then(setSolutions).catch(() => {})
      return
    }
    esRef.current?.close()
    const es = new EventSource(`/api/v1/tasks/${currentTask.id}/events`)
    esRef.current = es
    es.onmessage = (ev) => {
      try {
        const d = JSON.parse(ev.data)
        if (d.type === 'snapshot' || d.type === 'progress') {
          setCurrentTask((p) => (p ? { ...p, progress: d.percent ?? p.progress, stage: d.stage ?? p.stage, status: d.status ?? p.status } : p))
        }
        if (d.type === 'done' || d.type === 'failed' || d.type === 'cancelled') {
          api('GET', `/tasks/${currentTask.id}`).then((t) => { setCurrentTask(t) }).catch(() => {})
          api('GET', `/tasks/${currentTask.id}/solutions`).then(setSolutions).catch(() => {})
          es.close()
        }
      } catch { /* ignore */ }
    }
    return () => es.close()
  }, [view, currentTask?.id])

  if (!authed) {
    return (
      <div className="app">
        <div className="header"><h1>OR-Scheduling-SaaS 智能排程</h1></div>
        <div className="card" style={{ maxWidth: 420, margin: '40px auto' }}>
          <h3>{mode === 'login' ? '登录' : '注册'}</h3>
          {error && <div className="error">{error}</div>}
          {info && <div className="success">{info}</div>}
          <label>邮箱</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
          <label>密码（≥8 位）</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn" onClick={doAuth}>{mode === 'login' ? '登录' : '注册'}</button>
            <button className="btn secondary" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); setInfo('') }}>
              {mode === 'login' ? '去注册' : '去登录'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="app">
      <div className="header">
        <h1>OR-Scheduling-SaaS 智能排程</h1>
        <div className="row" style={{ flex: 'none' }}>
          <button className="btn secondary" onClick={() => { setView('tasks'); loadTasks() }}>任务列表</button>
          <button className="btn secondary" onClick={() => { setView('submit'); loadDatasets() }}>提交任务</button>
          <button className="btn danger" onClick={logout}>退出</button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {info && <div className="success">{info}</div>}

      {view === 'tasks' && (
        <div className="card">
          <h3>任务列表</h3>
          <table>
            <thead><tr><th>名称</th><th>状态</th><th>进度</th><th>求解器</th><th>ΣT</th><th>操作</th></tr></thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td><span className={`badge ${t.status}`}>{t.status}</span></td>
                  <td style={{ width: 160 }}>
                    <div className="progress-bar"><div className="progress-fill" style={{ width: `${(t.progress || 0) * 100}%` }} /></div>
                  </td>
                  <td>{t.solver || '-'}</td>
                  <td>{t.objective?.tardiness ?? '-'}</td>
                  <td><button className="btn secondary" onClick={() => openTask(t)}>查看</button></td>
                </tr>
              ))}
              {tasks.length === 0 && <tr><td colSpan={6} style={{ textAlign: 'center', color: '#999' }}>暂无任务</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {view === 'submit' && (
        <>
          <div className="card">
            <h3>上传数据集（约束配置）</h3>
            <div className="row">
              <div><label>数据集名称</label><input value={dsName} onChange={(e) => setDsName(e.target.value)} placeholder="周二排程" /></div>
            </div>
            <label>五 JSON 合并（machines / orders / recipes / switch_matrix）</label>
            <textarea rows={8} value={dsJson} onChange={(e) => setDsJson(e.target.value)}
              placeholder='{"machines":[...],"orders":[...],"recipes":[...],"switch_matrix":{"recipes":[...],"matrix":[...]}}' />
            <button className="btn" onClick={uploadDataset}>上传数据集</button>
          </div>

          <div className="card">
            <h3>提交求解任务</h3>
            <div className="row">
              <div><label>任务名称</label><input value={taskName} onChange={(e) => setTaskName(e.target.value)} placeholder="周二排程求解" /></div>
              <div>
                <label>数据集</label>
                <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
                  <option value="">选择数据集</option>
                  {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}（{d.num_orders}单×{d.num_machines}机）</option>)}
                </select>
              </div>
            </div>
            <div className="row">
              <div><label>目标权重 λ（makespan, tardiness, completion）</label><input value={lambda} onChange={(e) => setLambda(e.target.value)} /></div>
              <div>
                <label>求解器</label>
                <select value={solver} onChange={(e) => setSolver(e.target.value)}>
                  <option value="auto">自动（规模路由）</option>
                  <option value="cpsat">CP-SAT 精确</option>
                  <option value="alns">构造+ALNS</option>
                  <option value="all">全部对比（CP-SAT+ALNS）</option>
                </select>
              </div>
              <div><label>时间预算（秒，可选）</label><input value={timeBudget} onChange={(e) => setTimeBudget(e.target.value)} placeholder="空=默认" /></div>
            </div>
            <button className="btn" onClick={submitTask} disabled={!datasetId || !taskName}>提交任务</button>
          </div>
        </>
      )}

      {view === 'detail' && currentTask && (
        <div className="card">
          <h3>任务详情：{currentTask.name}</h3>
          <div className="row" style={{ marginBottom: 12 }}>
            <div><span className={`badge ${currentTask.status}`}>{currentTask.status}</span></div>
            <div>阶段：{currentTask.stage || '-'}</div>
            <div style={{ flex: 2 }}>
              <div className="progress-bar"><div className="progress-fill" style={{ width: `${(currentTask.progress || 0) * 100}%` }} /></div>
            </div>
            <div>{Math.round((currentTask.progress || 0) * 100)}%</div>
          </div>
          {currentTask.objective && (
            <div style={{ fontSize: 13, color: '#555', marginBottom: 12 }}>
              目标：makespan={currentTask.objective.makespan ?? '-'} · ΣT={currentTask.objective.tardiness ?? '-'} · ΣC={currentTask.objective.completion ?? '-'}
            </div>
          )}

          {solutions.length > 0 && (
            <>
              <h4>方案对比（{solutions.length}）</h4>
              <table>
                <thead><tr><th>引擎</th><th>状态</th><th>makespan</th><th>ΣT</th><th>ΣC</th><th>gap</th><th>耗时</th><th>甘特图</th></tr></thead>
                <tbody>
                  {solutions.map((s) => (
                    <tr key={s.id} style={{ background: s.id === activeSol ? '#eef2ff' : 'transparent' }}>
                      <td>{s.engine}</td>
                      <td>{s.status}</td>
                      <td>{s.objective.makespan ?? '-'}</td>
                      <td>{s.objective.tardiness ?? '-'}</td>
                      <td>{s.objective.completion ?? '-'}</td>
                      <td>{s.gap != null ? s.gap.toFixed(3) : '-'}</td>
                      <td>{s.solve_time_s.toFixed(2)}s</td>
                      <td><button className="btn secondary" onClick={() => loadSolution(s.id)}>查看</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {gantt && <div style={{ marginTop: 16 }}><h4>甘特图（{gantt.meta.solver}）</h4><Gantt data={gantt} /></div>}
            </>
          )}
        </div>
      )}
    </div>
  )
}
