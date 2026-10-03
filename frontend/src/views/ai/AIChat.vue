<template>
    <div class="ai-chat-layout">
        <aside class="ai-chat-sidebar">
            <div class="sidebar-header">
                <button type="button" class="new-chat-btn" :disabled="loading" @click="handleNewChat">
                    <svg class="new-chat-icon" viewBox="0 0 24 24" aria-hidden="true">
                        <circle cx="12" cy="12" r="7.25" fill="none" stroke="currentColor" stroke-width="1.8" />
                        <path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
                            stroke-linejoin="round" d="m9.6 18.2-1.1 1.6" />
                        <path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
                            d="M12 9v6M9 12h6" />
                    </svg>
                    <span class="new-chat-text">开启新对话</span>
                </button>
            </div>
            <div class="sidebar-list" v-loading="sessionsLoading">
                <div v-if="!sessions.length && !sessionsLoading" class="sidebar-empty">
                    <el-icon class="sidebar-empty-icon">
                        <ChatDotRound />
                    </el-icon>
                    <p>暂无会话</p>
                    <span>发一条消息开始新对话</span>
                </div>
                <div v-for="item in sessions" :key="item.thread_id" class="session-item"
                    :class="{ active: item.thread_id === threadId }" @click="handleSelectSession(item)">
                    <div class="session-title">{{ item.title || '新对话' }}</div>
                    <div class="session-meta">
                        <span>{{ formatTime(item.update_time || item.create_time) }}</span>
                        <div class="session-actions">
                            <button type="button" class="session-action" :disabled="loading" title="重命名"
                                @click.stop="handleRenameSession(item)">
                                <el-icon>
                                    <EditPen />
                                </el-icon>
                            </button>
                            <button type="button" class="session-action is-danger" :disabled="loading" title="删除"
                                @click.stop="handleDeleteSession(item)">
                                <el-icon>
                                    <Delete />
                                </el-icon>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </aside>

        <section class="ai-chat-main">
            <div ref="listRef" class="message-list">
                <div v-for="(item, index) in messages" :key="index" class="msg-row"
                    :class="item.role === 'user' ? 'is-user' : 'is-assistant'">
                    <div class="msg-bubble" v-html="parseMarkdown(item.content)"></div>
                </div>
                <div v-if="loading && !streamingAssistant && messages.length && messages[messages.length - 1].role === 'user'"
                    class="msg-row is-assistant">
                    <div class="msg-bubble typing">
                        <span></span><span></span><span></span>
                    </div>
                </div>
            </div>

            <div class="composer">
                <div class="composer-box">
                    <el-input v-model="input" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" resize="none"
                        placeholder="问问实验室怎么预约、开放时间" @keydown.enter.exact.prevent="handleSend"
                        @keydown.enter.shift.stop />
                    <div class="composer-toolbar">
                        <span v-if="loading" class="composer-hint">停止后后端可能仍跑完</span>
                        <button v-if="!loading" type="button" class="send-btn" :class="{ ready: canSend }"
                            :disabled="!canSend" title="发送" @click="handleSend">
                            <el-icon :size="18">
                                <Top />
                            </el-icon>
                        </button>
                        <button v-else type="button" class="send-btn ready" title="停止生成（停止后后端可能仍跑完）"
                            @click="handleStop">
                            <span class="stop-icon"></span>
                        </button>
                    </div>
                </div>
            </div>
        </section>
    </div>
</template>

<script setup>
import {
    chatStreamApi,
    listSessionsApi,
    getSessionMessagesApi,
    deleteSessionApi,
    updateSessionApi
} from '@/api/ai'
import { ref, nextTick, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, EditPen, ChatDotRound, Top } from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const WELCOME = {
    role: 'assistant',
    content:
        '你好，我是实验室预约助手。可以问规则和开放实验室，也可以说「帮我预约明天下午的实验室」，确认后我会帮你提交。'
}

const messages = ref([WELCOME])
const input = ref('')
const loading = ref(false)
const listRef = ref()
const threadId = ref(null)
const sessions = ref([])
const sessionsLoading = ref(false)
const streamingAssistant = ref(false) // 已有首个 delta 后关掉 typing 三点
let loadToken = 0
let abortController = null // 停止生成：只 abort 读流
let markdownRaf = 0 // 流式 Markdown 节流，避免每 token 全量 parse

const canSend = computed(() => !!input.value.trim() && !loading.value)

/** 滚动消息列表到底部 */
const scrollToBottom = () => {
    nextTick(() => {
        const elem = listRef.value
        if (elem) elem.scrollTop = elem.scrollHeight
    })
}

/** 重置为欢迎语（新会话） */
const resetWelcome = () => {
    messages.value = [{ ...WELCOME }]
}

/** 侧栏时间截取为月日时分 */
const formatTime = (value) => {
    if (!value) return ''
    const s = String(value)
    // 期望 "YYYY-MM-DD HH:mm:ss"，侧栏只显示月日时分
    if (s.length >= 16) return s.slice(5, 16)
    return s
}

/** 刷新侧栏会话列表 */
const refreshSessions = async () => {
    sessionsLoading.value = true
    try {
        const res = await listSessionsApi()
        if (res.code === 200) {
            sessions.value = res.data || []
        }
    } finally {
        sessionsLoading.value = false
    }
}

/** 开启新会话（清空 thread_id 与消息） */
const handleNewChat = () => {
    if (loading.value) return
    threadId.value = null
    resetWelcome()
    scrollToBottom()
}

/** 切换会话并拉取历史；用 loadToken 丢弃过期响应 */
const handleSelectSession = async (item) => {
    if (loading.value) return
    if (!item?.thread_id || item.thread_id === threadId.value) return
    const token = ++loadToken
    threadId.value = item.thread_id
    loading.value = true
    try {
        const res = await getSessionMessagesApi(item.thread_id)
        if (token !== loadToken) return
        if (res.code === 200) {
            const list = (res.data || []).map((m) => ({
                role: m.role,
                content: m.content
            }))
            messages.value = list.length ? list : [{ ...WELCOME }]
            scrollToBottom()
        }
    } finally {
        if (token === loadToken) loading.value = false
    }
}

/** 弹窗修改会话标题 */
const handleRenameSession = async (item) => {
    if (loading.value || !item?.thread_id) return
    let title
    try {
        const { value } = await ElMessageBox.prompt('请输入新的会话名称', '重命名', {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            inputValue: item.title || '新对话',
            inputValidator: (val) => {
                const t = (val || '').trim()
                if (!t) return '标题不能为空'
                if (t.length > 100) return '标题最多 100 字'
                return true
            }
        })
        title = (value || '').trim()
    } catch {
        return
    }
    if (!title || title === (item.title || '').trim()) return
    const res = await updateSessionApi(item.thread_id, { title })
    if (res.code === 200) {
        ElMessage.success('已重命名')
        await refreshSessions()
    }
}

/** 确认后软删会话；若为当前会话则回到欢迎页 */
const handleDeleteSession = async (item) => {
    if (loading.value || !item?.thread_id) return
    try {
        await ElMessageBox.confirm('确定删除该会话吗？', '提示', { type: 'warning' })
    } catch {
        return
    }
    const res = await deleteSessionApi(item.thread_id)
    if (res.code === 200) {
        if (threadId.value === item.thread_id) {
            handleNewChat()
        }
        await refreshSessions()
    }
}

/** 停止读 SSE（abort 不取消后端 LLM / 工具，预约等副作用可能已发生） */
const handleStop = () => {
    abortController?.abort()
}

/** 主路径走 /chat/stream：乐观插入 user，按 delta 涨气泡，done 后校正并刷新侧栏 */
const handleSend = async () => {
    const text = input.value.trim()
    if (!text || loading.value) return
    messages.value.push({ role: 'user', content: text })
    input.value = ''
    loading.value = true
    streamingAssistant.value = false
    scrollToBottom()
    abortController = new AbortController()
    let assistantIndex = -1
    let assembled = ''
    /** 把内存里拼好的字刷到当前 assistant 气泡（配合 rAF 节流） */
    const flushAssistant = () => {
        markdownRaf = 0
        if (assistantIndex >= 0) {
            messages.value[assistantIndex].content = assembled
            scrollToBottom()
        }
    }
    /** 收到一块 delta.content：首包建气泡，之后追加 */
    const applyDelta = (piece) => {
        if (!piece) return
        assembled += piece
        if (assistantIndex < 0) {
            streamingAssistant.value = true
            messages.value.push({ role: 'assistant', content: assembled })
            assistantIndex = messages.value.length - 1
            scrollToBottom()
            return
        }
        if (!markdownRaf) {
            markdownRaf = requestAnimationFrame(flushAssistant)
        }
    }
    try {
        const payload = {
            messages: [{ role: 'user', content: text }],
            thread_id: threadId.value || null
        }
        await chatStreamApi(payload, {
            signal: abortController.signal,
            onMeta: (data) => {
                if (data?.thread_id) threadId.value = data.thread_id
            },
            onDelta: (data) => applyDelta(data?.content || ''),
            onDone: async (data) => {
                if (data?.thread_id) threadId.value = data.thread_id
                const full = data?.content || assembled
                assembled = full
                if (assistantIndex < 0 && full) {
                    messages.value.push({ role: data?.role || 'assistant', content: full })
                    assistantIndex = messages.value.length - 1
                } else if (assistantIndex >= 0) {
                    messages.value[assistantIndex].content = full
                }
                scrollToBottom()
                await refreshSessions()
            },
            onError: async (err) => {
                ElMessage.error(err?.message || '大模型调用失败，请稍后重试')
                if (!threadId.value) return
                try {
                    const res = await getSessionMessagesApi(threadId.value)
                    if (res?.code === 200 && Array.isArray(res.data) && res.data.length) {
                        const list = res.data.map((m) => ({
                            role: m.role,
                            content: m.content
                        }))
                        const last = list[list.length - 1]
                        if (last?.role === 'assistant' && last.content) {
                            messages.value = list
                        }
                    }
                } catch {
                    // 中断/失败时 MySQL 可能仍无 assistant，保留当前半截气泡
                }
            }
        })
    } catch (err) {
        // 用户点停止会 AbortError，不当成网络故障
        if (err?.name !== 'AbortError') {
            ElMessage.error(err?.message || '网络异常，请检查后端服务')
        }
    } finally {
        if (markdownRaf) {
            cancelAnimationFrame(markdownRaf)
            markdownRaf = 0
            flushAssistant()
        }
        loading.value = false
        streamingAssistant.value = false
        abortController = null
    }
}

/** Markdown 转安全 HTML（marked + DOMPurify） */
const parseMarkdown = (text) => {
    if (!text) return ''
    marked.setOptions({ breaks: true })
    const rawHtml = marked.parse(text)
    return DOMPurify.sanitize(rawHtml)
}

onMounted(async () => {
    await refreshSessions()
})
</script>

<style scoped>
.ai-chat-layout {
    --chat-primary: var(--el-color-primary, #409eff);
    --chat-primary-soft: color-mix(in srgb, var(--chat-primary) 12%, #fff);
    --chat-border: #e8edf3;
    --chat-surface: #ffffff;
    --chat-muted: #8a94a6;
    --chat-ink: #1f2a37;

    display: flex;
    gap: 14px;
    align-items: stretch;
    height: calc(100vh - 100px);
}

.ai-chat-sidebar {
    width: 248px;
    flex-shrink: 0;
    background: var(--chat-surface);
    border-radius: 12px;
    border: 1px solid var(--chat-border);
    box-shadow: 0 1px 2px rgba(31, 42, 55, 0.04);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-height: 0;
}

.sidebar-header {
    display: flex;
    align-items: center;
    padding: 12px;
    border-bottom: 1px solid var(--chat-border);
    flex-shrink: 0;
    background: #fff;
}

.new-chat-btn {
    width: 100%;
    height: 40px;
    border: 0;
    border-radius: 999px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    padding: 0 16px;
    margin: 0;
    cursor: pointer;
    color: #fff;
    background: var(--chat-primary);
    font: 500 14px/1 var(--el-font-family, inherit);
    letter-spacing: 0.02em;
    box-sizing: border-box;
    -webkit-appearance: none;
    appearance: none;
    transition: background-color 0.15s ease, opacity 0.15s ease, transform 0.15s ease;
}

.new-chat-btn:hover:not(:disabled) {
    background: var(--el-color-primary-dark-2, #0d5f59);
}

.new-chat-btn:active:not(:disabled) {
    transform: scale(0.98);
}

.new-chat-btn:disabled {
    opacity: 0.55;
    cursor: not-allowed;
}

.new-chat-icon {
    width: 20px;
    height: 20px;
    flex: none;
    display: block;
}

.new-chat-text {
    flex: none;
    line-height: 1;
}

.sidebar-list {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
    padding: 10px;
}

.sidebar-empty {
    color: var(--chat-muted);
    text-align: center;
    padding: 40px 12px;
}

.sidebar-empty-icon {
    font-size: 28px;
    color: #c0c8d4;
    margin-bottom: 8px;
}

.sidebar-empty p {
    margin: 0;
    font-size: 13px;
    color: #606266;
}

.sidebar-empty span {
    display: block;
    margin-top: 6px;
    font-size: 12px;
}

.session-item {
    padding: 10px 12px;
    border-radius: 10px;
    cursor: pointer;
    margin-bottom: 6px;
    border: 1px solid transparent;
    background: #f5f8fb;
    transition: background-color 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
}

.session-item:hover {
    background: #eef3f8;
}

.session-item.active {
    background: var(--chat-primary-soft);
    border-color: color-mix(in srgb, var(--chat-primary) 28%, #fff);
}

.session-title {
    font-size: 13px;
    font-weight: 550;
    color: var(--chat-ink);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.session-meta {
    margin-top: 6px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    font-size: 12px;
    color: var(--chat-muted);
}

.session-actions {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    opacity: 0;
    transition: opacity 0.15s ease;
}

.session-item:hover .session-actions,
.session-item.active .session-actions {
    opacity: 1;
}

.session-action {
    border: none;
    background: transparent;
    color: #a8b0bd;
    cursor: pointer;
    padding: 2px;
    border-radius: 4px;
    display: inline-flex;
    align-items: center;
    transition: color 0.15s ease, background-color 0.15s ease;
}

.session-action:hover:not(:disabled) {
    color: var(--chat-primary);
    background: color-mix(in srgb, var(--chat-primary) 10%, transparent);
}

.session-action.is-danger:hover:not(:disabled) {
    color: #f56c6c;
    background: rgba(245, 108, 108, 0.08);
}

.session-action:disabled {
    cursor: not-allowed;
}

.ai-chat-main {
    flex: 1;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    background: var(--chat-surface);
    border: 1px solid var(--chat-border);
    border-radius: 12px;
    box-shadow: 0 1px 2px rgba(31, 42, 55, 0.04);
    overflow: hidden;
}

.chat-header {
    padding: 14px 18px;
    border-bottom: 1px solid var(--el-card-border-color, #ebeef5);
    background: #fff;
    flex-shrink: 0;
    font-size: 16px;
    font-weight: bold;
    color: #303133;
}

.message-list {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
    padding: 18px 16px 8px;
    background:
        radial-gradient(1200px 400px at 10% -10%, rgba(64, 158, 255, 0.07), transparent 55%),
        linear-gradient(180deg, #f4f7fb 0%, #f7f9fc 100%);
}

.msg-row {
    display: flex;
    align-items: flex-end;
    margin-bottom: 14px;
}

.msg-row.is-user {
    justify-content: flex-end;
}

.msg-row.is-assistant {
    justify-content: flex-start;
}

.msg-bubble {
    max-width: min(72%, 640px);
    padding: 10px 14px;
    border-radius: 14px;
    line-height: 1.65;
    font-size: 14px;
    word-break: break-word;
    box-shadow: 0 1px 2px rgba(31, 42, 55, 0.05);
}

.msg-row.is-assistant .msg-bubble {
    background: #fff;
    color: #303133;
    border: 1px solid #eef2f7;
    border-bottom-left-radius: 5px;
}

.msg-row.is-user .msg-bubble {
    background: linear-gradient(145deg, #4ea3ff, #3a8ee6);
    color: #fff;
    border-bottom-right-radius: 5px;
}

.msg-bubble :deep(p) {
    margin: 0 0 0.55em;
}

.msg-bubble :deep(p:last-child) {
    margin-bottom: 0;
}

.msg-bubble :deep(ul),
.msg-bubble :deep(ol) {
    margin: 0.4em 0;
    padding-left: 1.25em;
}

.msg-bubble :deep(code) {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.92em;
    padding: 0.1em 0.35em;
    border-radius: 4px;
    background: rgba(0, 0, 0, 0.06);
}

.msg-row.is-user .msg-bubble :deep(code) {
    background: rgba(255, 255, 255, 0.2);
}

.msg-bubble :deep(a) {
    color: inherit;
    text-decoration: underline;
}

.msg-bubble.typing {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    min-height: 20px;
    padding: 12px 16px;
}

.msg-bubble.typing span {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #a0aec0;
    animation: typing-bounce 1.1s infinite ease-in-out;
}

.msg-bubble.typing span:nth-child(2) {
    animation-delay: 0.15s;
}

.msg-bubble.typing span:nth-child(3) {
    animation-delay: 0.3s;
}

@keyframes typing-bounce {

    0%,
    80%,
    100% {
        transform: translateY(0);
        opacity: 0.45;
    }

    40% {
        transform: translateY(-4px);
        opacity: 1;
    }
}

.composer {
    margin: 0;
    padding: 12px 14px 14px;
    flex-shrink: 0;
    border-top: 1px solid var(--chat-border);
    background: #fff;
}

.composer-box {
    display: flex;
    flex-direction: column;
    border: 1px solid #e4eaf1;
    border-radius: 18px;
    background: #f7f9fc;
    overflow: hidden;
    transition: border-color 0.15s ease, box-shadow 0.15s ease, background-color 0.15s ease;
}

.composer-box:focus-within {
    background: #fff;
    border-color: color-mix(in srgb, var(--chat-primary) 55%, #e4eaf1);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--chat-primary) 12%, transparent);
}

.composer :deep(.el-textarea__inner) {
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    border-radius: 0;
    padding: 14px 16px 6px;
    min-height: 52px;
    line-height: 1.55;
}

.composer-toolbar {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 12px;
    padding: 6px 10px 10px 16px;
}

.composer-hint {
    font-size: 12px;
    color: var(--chat-muted);
    user-select: none;
}

.send-btn {
    width: 34px;
    height: 34px;
    border: none;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    cursor: pointer;
    color: #fff;
    background: #9aa7b8;
    transition: background-color 0.15s ease, transform 0.15s ease, opacity 0.15s ease;
}

.send-btn.ready {
    background: var(--chat-primary, #409eff);
}

.send-btn:hover:not(:disabled) {
    transform: scale(1.04);
}

.send-btn:disabled {
    cursor: not-allowed;
    opacity: 0.72;
}

.stop-icon {
    width: 10px;
    height: 10px;
    border-radius: 2px;
    background: #fff;
    display: block;
}

@media (max-width: 768px) {
    .ai-chat-layout {
        flex-direction: column;
        height: auto;
        min-height: 0;
    }

    .ai-chat-sidebar {
        width: 100%;
        max-height: 220px;
    }

    .ai-chat-main {
        min-height: 480px;
        height: calc(100vh - 380px);
    }

    .msg-bubble {
        max-width: 85%;
    }
}
</style>
