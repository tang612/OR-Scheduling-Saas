const BASE = '/api/v1'

let token: string | null = localStorage.getItem('token')

export function setToken(t: string | null) {
  token = t
  if (t) localStorage.setItem('token', t)
  else localStorage.removeItem('token')
}

export function getToken() {
  return token
}

export async function api(method: string, path: string, body?: unknown): Promise<any> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const resp = await fetch(BASE + path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (resp.status === 204) return null
  const data = await resp.json().catch(() => null)
  if (!resp.ok) {
    const msg = typeof data?.detail === 'string' ? data.detail : JSON.stringify(data?.detail || data || '请求失败')
    throw new Error(msg)
  }
  return data
}

/** 带鉴权的文件下载（fetch blob → 触发浏览器下载，日志导出用）。 */
export async function downloadText(path: string, filename: string): Promise<void> {
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  const resp = await fetch(BASE + path, { headers })
  if (!resp.ok) throw new Error(`下载失败（${resp.status}）`)
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
