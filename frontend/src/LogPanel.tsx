import { useEffect, useMemo, useRef, useState } from 'react'
import { downloadText } from './api'

const ROW_H = 20
const VIEW_H = 440
const OVERSCAN = 20

type Level = 'all' | 'info' | 'warning' | 'error'

function levelOf(line: string): Exclude<Level, 'all'> {
  if (/error/i.test(line)) return 'error'
  if (/warn|warning/i.test(line)) return 'warning'
  return 'info'
}

/** 实时求解日志面板：虚拟列表（10000 行无卡顿）+ 级别过滤 + 搜索 + 自动滚动 + 导出 */
export default function LogPanel({
  taskId, logs, engine, running,
}: {
  taskId: string
  logs: string[]
  engine?: string
  running: boolean
}) {
  const [level, setLevel] = useState<Level>('all')
  const [query, setQuery] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [downloadErr, setDownloadErr] = useState('')
  const boxRef = useRef<HTMLDivElement | null>(null)

  const filtered = useMemo(() => {
    let ls = logs
    if (level !== 'all') ls = ls.filter((l) => levelOf(l) === level)
    if (query.trim()) {
      const q = query.trim().toLowerCase()
      ls = ls.filter((l) => l.toLowerCase().includes(q))
    }
    return ls
  }, [logs, level, query])

  // 虚拟列表窗口
  const [scrollTop, setScrollTop] = useState(0)
  const total = filtered.length
  const start = Math.max(0, Math.floor(scrollTop / ROW_H) - OVERSCAN)
  const end = Math.min(total, Math.ceil((scrollTop + VIEW_H) / ROW_H) + OVERSCAN)
  const visible = filtered.slice(start, end)

  // 自动滚动：新日志到达且用户未上滚时跟随底部
  useEffect(() => {
    const box = boxRef.current
    if (box && autoScroll) box.scrollTop = box.scrollHeight
  }, [logs.length, autoScroll])

  const onScroll = () => {
    const box = boxRef.current
    if (!box) return
    const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - ROW_H * 3
    setAutoScroll(atBottom)
    setScrollTop(box.scrollTop)
  }

  const goLatest = () => {
    setAutoScroll(true)
    const box = boxRef.current
    if (box) box.scrollTop = box.scrollHeight
  }

  const doDownload = async () => {
    try {
      setDownloadErr('')
      await downloadText(`/tasks/${taskId}/logs.txt`, `task-${taskId}-logs.txt`)
    } catch (e: any) {
      setDownloadErr(e.message || '下载失败')
    }
  }

  const isExact = engine?.includes('CP-SAT') || engine === 'cpsat'
  const emptyHint = !isExact
    ? '该求解器不产生实时求解日志，优化过程见「优化分析」Tab'
    : running
      ? '日志实时推送中，求解器输出将逐行追加…'
      : '该任务无日志记录'

  const highlight = (line: string) => {
    if (!query.trim()) return line
    const idx = line.toLowerCase().indexOf(query.trim().toLowerCase())
    if (idx < 0) return line
    return (
      <>
        {line.slice(0, idx)}
        <mark>{line.slice(idx, idx + query.length)}</mark>
        {line.slice(idx + query.length)}
      </>
    )
  }

  return (
    <div className="log-panel">
      <div className="log-toolbar">
        <div className="log-filters">
          {(['all', 'info', 'warning', 'error'] as Level[]).map((lv) => (
            <button
              key={lv}
              className={`btn secondary small ${level === lv ? 'active' : ''}`}
              onClick={() => setLevel(lv)}
            >
              {lv === 'all' ? '全部' : lv === 'info' ? 'INFO' : lv === 'warning' ? 'WARNING' : 'ERROR'}
              <span className={`log-count count-${lv}`}>
                {lv === 'all' ? logs.length : logs.filter((l) => levelOf(l) === lv).length}
              </span>
            </button>
          ))}
        </div>
        <div className="log-actions">
          <input
            className="log-search"
            placeholder="搜索日志关键词…"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setScrollTop(0) }}
          />
          <button className="btn secondary small" onClick={doDownload}>导出 TXT</button>
        </div>
      </div>
      {downloadErr && <div className="error">{downloadErr}</div>}

      <div
        ref={boxRef}
        className="log-virtual"
        style={{ height: VIEW_H }}
        onScroll={onScroll}
      >
        {total === 0 ? (
          <div className="empty-mini">{emptyHint}</div>
        ) : (
          <>
            <div style={{ height: start * ROW_H }} />
            {visible.map((line, i) => {
              const lv = levelOf(line)
              return (
                <div
                  key={start + i}
                  className={`log-row lv-${lv}`}
                  style={{ height: ROW_H }}
                  title={line}
                >
                  <span className="log-level">{lv === 'info' ? 'I' : lv === 'warning' ? 'W' : 'E'}</span>
                  <span className="log-line">{highlight(line)}</span>
                </div>
              )
            })}
            <div style={{ height: (total - end) * ROW_H }} />
          </>
        )}
      </div>

      {!autoScroll && total > 0 && (
        <button className="btn primary small go-latest" onClick={goLatest}>↓ 回到最新</button>
      )}
      <div className="log-meta">
        {running && isExact && <span className="live-dot">●</span>}
        共 {total.toLocaleString()} 行{level !== 'all' ? `（已按级别过滤）` : ''}
      </div>
    </div>
  )
}
