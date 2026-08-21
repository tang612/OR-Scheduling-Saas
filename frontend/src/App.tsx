import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { api, setToken, getToken } from './api'
import Dashboard from './Dashboard'
import type { Task } from './types'

interface Dataset { id: string; name: string; num_orders: number; num_machines: number; num_recipes: number }

const DS_FIELDS = ['machines', 'orders', 'recipes', 'switch_matrix']
const TEMPLATE_KEY = 'dataset_template'

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
  const [loading, setLoading] = useState(false)

  // 提交表单
  const [taskName, setTaskName] = useState('')
  const [datasetId, setDatasetId] = useState('')
  const [lambda, setLambda] = useState('0,1,0')
  const [solver, setSolver] = useState('auto')
  const [timeBudget, setTimeBudget] = useState('')

  // 数据集上传
  const [dsName, setDsName] = useState('')
  const [dsJson, setDsJson] = useState('')
  const [dsError, setDsError] = useState('')
  const [dragOver, setDragOver] = useState(false)

  // 详情
  const [currentTask, setCurrentTask] = useState<Task | null>(null)

  const loadTasks = useCallback(async () => {
    setLoading(true)
    try { setTasks(await api('GET', '/tasks')) } catch (e: any) { setError(e.message) } finally { setLoading(false) }
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

  // ---- 数据集：实时校验 + 模板 ----
  const onDsJsonChange = (val: string) => {
    setDsJson(val)
    if (!val.trim()) { setDsError(''); return }
    try {
      const d = JSON.parse(val)
      const missing = DS_FIELDS.filter((k) => !d[k])
      setDsError(missing.length ? `缺少字段：${missing.join('、')}` : '')
    } catch (e: any) {
      setDsError('JSON 语法错误：' + e.message)
    }
  }

  const readFileText = (f: File) => new Promise<string>((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(r.result as string)
    r.onerror = () => reject(new Error('读取失败：' + f.name))
    r.readAsText(f)
  })

  const handleFiles = async (files: FileList | File[]) => {
    setError(''); setInfo('')
    const list = Array.from(files).filter((f) => f.name.toLowerCase().endsWith('.json'))
    if (list.length === 0) { setError('请拖入 .json 文件'); return }
    try {
      if (list.length === 1) {
        // 单个文件：合并格式（含 machines/orders/recipes/switch_matrix 四字段）
        const text = await readFileText(list[0])
        const d = JSON.parse(text)
        if (d.machines && d.orders && d.recipes && d.switch_matrix) {
          onDsJsonChange(JSON.stringify(d, null, 2))
          if (!dsName.trim()) setDsName(list[0].name.replace(/\.json$/i, ''))
          setInfo('已导入：' + list[0].name)
        } else {
          setError('文件需含 machines/orders/recipes/switch_matrix 四字段（合并格式）')
        }
      } else {
        // 多文件：按文件名匹配 machines/orders/recipes/switch_matrix 自动合并
        const merged: Record<string, unknown> = {}
        for (const f of list) {
          const text = await readFileText(f)
          const d = JSON.parse(text)
          const base = f.name.replace(/\.json$/i, '').toLowerCase()
          if (base === 'machines' || base === 'orders' || base === 'recipes' || base === 'switch_matrix') {
            merged[base] = d
          } else if (base !== 'metadata') {
            merged[base] = d
          }
        }
        if (merged.machines && merged.orders && merged.recipes && merged.switch_matrix) {
          onDsJsonChange(JSON.stringify(merged, null, 2))
          if (!dsName.trim()) setDsName('导入数据集')
          setInfo(`已导入 ${list.length} 个文件并自动合并`)
        } else {
          setError('多文件需包含 machines.json / orders.json / recipes.json / switch_matrix.json')
        }
      }
    } catch (e: any) {
      setError('文件解析失败：' + e.message)
    }
  }

  const saveTemplate = () => {
    if (dsError) { setError('JSON 校验未通过，无法保存模板'); return }
    if (!dsJson.trim()) { setError('请先输入数据集 JSON'); return }
    localStorage.setItem(TEMPLATE_KEY, dsJson)
    setInfo('数据集模板已保存到本地')
  }

  const loadTemplate = () => {
    const t = localStorage.getItem(TEMPLATE_KEY)
    if (!t) { setInfo('暂无已保存的模板'); return }
    onDsJsonChange(t)
    setInfo('模板已加载')
  }

  const uploadDataset = async () => {
    setError(''); setInfo('')
    try {
      const d = JSON.parse(dsJson)
      if (!d.machines || !d.orders || !d.recipes || !d.switch_matrix) throw new Error('JSON 需含 machines/orders/recipes/switch_matrix')
      const r = await api('POST', '/datasets', { name: dsName, ...d })
      setInfo(`数据集已上传（${r.num_orders} 单 × ${r.num_machines} 机）`)
      setDsName(''); setDsJson(''); setDsError('')
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
      setView('detail'); setCurrentTask(r)
    } catch (e: any) { setError(e.message) }
  }

  const openTask = (t: Task) => {
    setView('detail'); setCurrentTask(t)
  }

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
          {loading ? (
            <div className="empty"><span className="empty-icon">⏳</span>加载中…</div>
          ) : tasks.length === 0 ? (
            <div className="empty"><span className="empty-icon">📋</span>暂无任务，去「提交任务」创建一个吧</div>
          ) : (
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
                    <td><button className="btn secondary small" onClick={() => openTask(t)}>查看</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {view === 'submit' && (
        <>
          <div className="card">
            <h3>上传数据集（约束配置）</h3>
            <div className="row">
              <div><label>数据集名称</label><input value={dsName} onChange={(e) => setDsName(e.target.value)} placeholder="周二排程" /></div>
            </div>
            <div
              className={`drop-zone ${dragOver ? 'dragover' : ''}`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files) }}
            >
              <span className="drop-zone-icon">📁</span>
              <div>拖拽 JSON 文件到此处（支持合并格式单文件，或 machines/orders/recipes/switch_matrix 多文件自动合并）</div>
              <label className="btn secondary small" style={{ marginTop: 8, cursor: 'pointer', display: 'inline-block' }}>
                选择文件
                <input type="file" accept=".json,application/json" multiple hidden onChange={(e) => { if (e.target.files) handleFiles(e.target.files); e.target.value = '' }} />
              </label>
            </div>
            <label>JSON 内容（拖拽/上传后自动填充，也可直接粘贴）</label>
            <textarea
              rows={8}
              value={dsJson}
              onChange={(e) => onDsJsonChange(e.target.value)}
              className={dsError ? 'textarea-error' : ''}
              placeholder='{"machines":[...],"orders":[...],"recipes":[...],"switch_matrix":{"recipes":[...],"matrix":[...]}}'
            />
            {dsError && <div className="field-error">⚠ {dsError}</div>}
            <div className="btn-group">
              <button className="btn" onClick={uploadDataset} disabled={!!dsError || !dsJson.trim() || !dsName.trim()}>上传数据集</button>
              <button className="btn secondary" onClick={saveTemplate}>保存模板</button>
              <button className="btn secondary" onClick={loadTemplate}>加载模板</button>
            </div>
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
        <Dashboard
          task={currentTask}
          onTaskUpdate={setCurrentTask}
          onBack={() => { setView('tasks'); loadTasks() }}
          onTasksChanged={loadTasks}
        />
      )}
    </div>
  )
}
