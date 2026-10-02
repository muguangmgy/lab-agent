import request from '@/utils/request'

/** 发送多轮对话（超时 60s；可带 thread_id） */
export function chatApi(data) {
  return request({
    url: '/api/ai/chat',
    method: 'post',
    data,
    timeout: 60000
  })
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
