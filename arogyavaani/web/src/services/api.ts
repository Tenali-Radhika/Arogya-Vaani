const API_BASE_URL = '/api'

export type Lang = 'hi-IN' | 'kn-IN' | 'en-IN'
export const LANG_LABEL: Record<Lang, string> = { 'hi-IN': 'हिन्दी', 'kn-IN': 'ಕನ್ನಡ', 'en-IN': 'English' }

export interface GetConfigResponse {
  app_id: string
  token: string
  uid: string
  channel_name: string
  agent_uid: string
  session_id: string
  patient_id: string
  lang: Lang
  patient_name: string
  elder_mode: boolean
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const error = await response.json()
      detail = typeof error.detail === 'string' ? error.detail : detail
    } catch {}
    throw new Error(detail)
  }
  return (await response.json()) as T
}

export async function getConfig(options?: {
  channel?: string
  uid?: string | number
  patient?: string
}): Promise<GetConfigResponse> {
  const params = new URLSearchParams()
  if (options?.channel) params.set('channel', options.channel)
  if (options?.uid !== undefined && options.uid !== '') params.set('uid', String(options.uid))
  if (options?.patient) params.set('patient', options.patient)
  const query = params.toString()
  const result = await parse<{ code: number; msg: string; data: GetConfigResponse }>(
    await fetch(`${API_BASE_URL}/get_config${query ? `?${query}` : ''}`),
  )
  if (result.code !== 0 || !result.data) throw new Error(result.msg || 'Failed to get configuration')
  return result.data
}

export interface StartOptions {
  sessionId: string
  patientId: string
  lang: Lang
  elderMode: boolean
}

export async function startAgent(
  channelName: string,
  rtcUid: number,
  userUid: number,
  opts: StartOptions,
): Promise<string> {
  const result = await parse<{ code: number; msg: string; data: { agent_id: string } }>(
    await fetch(`${API_BASE_URL}/session/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channelName, rtcUid, userUid, ...opts }),
    }),
  )
  if (result.code !== 0 || !result.data?.agent_id) throw new Error(result.msg || 'Failed to start agent')
  return result.data.agent_id
}

export async function stopAgent(sessionId: string): Promise<void> {
  if (!sessionId) return
  await parse(
    await fetch(`${API_BASE_URL}/session/${sessionId}/stop`, { method: 'POST' }),
  )
}

export async function setLanguage(sessionId: string, lang: Lang): Promise<{ ms?: number; swapped: boolean }> {
  const r = await parse<{ data: { ms?: number; swapped: boolean } }>(
    await fetch(`${API_BASE_URL}/session/${sessionId}/language`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lang }),
    }),
  )
  return r.data
}

export async function setElder(sessionId: string, on: boolean): Promise<void> {
  await fetch(`${API_BASE_URL}/session/${sessionId}/elder?on=${on}`, { method: 'POST' })
}

export async function acceptCall(
  followupId: number,
  channelName: string,
  rtcUid: number,
  userUid: number,
  sessionId: string,
): Promise<string> {
  const r = await parse<{ data: { agent_id: string } }>(
    await fetch(`${API_BASE_URL}/call/accept`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ followupId, channelName, rtcUid, userUid, sessionId }),
    }),
  )
  return r.data.agent_id
}

export interface InboxMessage {
  id: number
  recipient: string
  channel: string
  text: string
  media_url: string
  ics_url: string
  delivered: boolean
  created: number
}

export async function getInbox(patientId: string): Promise<InboxMessage[]> {
  const r = await parse<{ messages: InboxMessage[] }>(await fetch(`${API_BASE_URL}/inbox/${patientId}`))
  return r.messages
}

export async function getMetrics(): Promise<{ turns: number; p50_ms: number }> {
  return parse(await fetch(`${API_BASE_URL}/metrics`))
}

// ---- demo controls (?demo=1)
export const demo = {
  forceConflict: () => fetch(`${API_BASE_URL}/demo/force-conflict`, { method: 'POST' }).then((r) => r.json()),
  fastForward: () => fetch(`${API_BASE_URL}/demo/fast-forward`, { method: 'POST' }).then(parse),
  reset: () => fetch(`${API_BASE_URL}/demo/reset`, { method: 'POST' }).then(parse),
  seed: () => fetch(`${API_BASE_URL}/demo/seed`, { method: 'POST' }).then(parse),
}

// ---- nurse console
export async function consoleFetch<T>(path: string, password: string, init?: RequestInit): Promise<T> {
  return parse<T>(
    await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', 'X-Console-Password': password, ...(init?.headers ?? {}) },
    }),
  )
}

/** WebSocket URL for tool/UI events. Browsers can't use Next rewrites for ws, so go to the backend directly in dev. */
export function eventsUrl(channelId: string): string {
  const explicit = process.env.NEXT_PUBLIC_BACKEND_WS
  if (explicit) return `${explicit.replace(/\/$/, '')}/ws/events/${encodeURIComponent(channelId)}`
  const { protocol, hostname, port } = window.location
  const wsProto = protocol === 'https:' ? 'wss:' : 'ws:'
  const host = port === '3000' ? `${hostname}:8000` : window.location.host
  return `${wsProto}//${host}/ws/events/${encodeURIComponent(channelId)}`
}
