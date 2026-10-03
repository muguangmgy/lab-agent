import request from '@/utils/request'
import { getToken } from '@/utils/auth'

/** 发送多轮对话（超时 60s；可带 thread_id） */
export function chatApi(data) {
  return request({
    url: '/api/ai/chat',
    method: 'post',
    data,
    timeout: 60000
  })
}

/**
 * SSE 流式对话：独立 fetch + Bearer，不走 axios（避免 60s 超时和把流当 JSON）。
 * EventSource 无法自定义 Authorization，所以必须用 fetch。
 * @param {{ messages: Array, thread_id?: string|null }} data 与 /chat 相同的 ChatRequest
 * @param {{ signal?: AbortSignal, onMeta?: Function, onDelta?: Function, onDone?: Function, onError?: Function }} hooks
 *   signal：停止生成时 AbortController.abort()，只停读流，不保证取消后端
 */
export async function chatStreamApi(data, { signal, onMeta, onDelta, onDone, onError } = {}) {
  const token = getToken()
  const res = await fetch(
    (import.meta.env.VITE_API_BASE_URL || '') + '/api/ai/chat/stream',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      },
      body: JSON.stringify({
        messages: data.messages,
        thread_id: data.thread_id || null
      }),
      signal
    }
  )

  const contentType = res.headers.get('content-type') || ''
  // 进入 SSE 之前的业务错误仍是 JSON Response（鉴权 / 403 等）
  if (!contentType.includes('text/event-stream')) {
    let payload = { code: res.status, message: '请求失败' }
    try {
      payload = await res.json()
    } catch {
      // 非 JSON 时沿用默认
    }
    onError?.(payload)
    return payload
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  let eventName = ''
  let dataLine = ''

  /** 空行表示一帧结束：按 event 名回调 meta / delta / done / error */
  const dispatch = () => {
    if (!eventName && dataLine === '') return
    let payload = {}
    try {
      payload = dataLine ? JSON.parse(dataLine) : {}
    } catch {
      payload = { message: dataLine }
    }
    if (eventName === 'meta') onMeta?.(payload)
    else if (eventName === 'delta') onDelta?.(payload)
    else if (eventName === 'done') onDone?.(payload)
    else if (eventName === 'error') onError?.(payload)
    eventName = ''
    dataLine = ''
  }

  /** 解析单行：event: xxx / data: {json} / 空行结束帧 */
  const consumeLine = (line) => {
    if (line === '' || line === '\r') {
      dispatch()
      return
    }
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLine = line.slice(5).trimStart()
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? '' // 最后半行留到下一块
    for (const line of lines) {
      consumeLine(line.replace(/\r$/, ''))
    }
  }
  if (buf) consumeLine(buf.replace(/\r$/, ''))
  dispatch()
}

/** 拉取当前用户会话列表 */
export function listSessionsApi() {
  return request({
    url: '/api/ai/sessions',
    method: 'get'
  })
}

/** 新建 AI 会话 */
export function createSessionApi(data) {
  return request({
    url: '/api/ai/sessions',
    method: 'post',
    data: data || {}
  })
}

/** 按 thread_id 拉取会话历史消息 */
export function getSessionMessagesApi(threadId) {
  return request({
    url: `/api/ai/sessions/${threadId}/messages`,
    method: 'get'
  })
}

/** 软删指定会话 */
export function deleteSessionApi(threadId) {
  return request({
    url: `/api/ai/sessions/${threadId}`,
    method: 'delete'
  })
}

/** 更新会话标题等信息 */
export function updateSessionApi(threadId, data) {
  return request({
    url: `/api/ai/sessions/${threadId}`,
    method: 'patch',
    data
  })
}
