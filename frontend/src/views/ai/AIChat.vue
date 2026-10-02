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
                        <button type="button" class="session-delete" :disabled="loading" title="删除"
                            @click.stop="handleDeleteSession(item)">
                            <el-icon>
                                <Delete />
                            </el-icon>
                        </button>
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
                <div v-if="loading && messages.length && messages[messages.length - 1].role === 'user'"
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
                        <button type="button" class="send-btn" :class="{ ready: canSend }" :disabled="!canSend"
                            title="发送" @click="handleSend">
                            <el-icon v-if="!loading" :size="18">
                                <Top />
                            </el-icon>
                            <el-icon v-else class="is-loading" :size="18">
                                <Loading />
                            </el-icon>
                        </button>
                    </div>
                </div>
            </div>
        </section>
    </div>
</template>

<script setup>
import {
    chatApi,
    listSessionsApi,
    getSessionMessagesApi,
    deleteSessionApi
} from '@/api/ai'
import { ref, nextTick, onMounted, computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Delete, ChatDotRound, Top, Loading } from '@element-plus/icons-vue'
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
let loadToken = 0

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

/** 发送用户消息并追加助手回复（可带 thread_id） */
const handleSend = async () => {
    const text = input.value.trim()
    if (!text || loading.value) return
    messages.value.push({ role: 'user', content: text })
    input.value = ''
    loading.value = true
    scrollToBottom()
    try {
        const payload = {
            messages: [{ role: 'user', content: text }],
            thread_id: threadId.value || null
        }
        const res = await chatApi(payload)
        if (res.code === 200 && res.data) {
            if (res.data.thread_id) {
                threadId.value = res.data.thread_id
            }
            messages.value.push({
                role: res.data.role || 'assistant',
                content: res.data.content || ''
            })
            scrollToBottom()
            await refreshSessions()
        }
    } finally {
        loading.value = false
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

.session-delete {
    opacity: 0;
    border: none;
    background: transparent;
    color: #a8b0bd;
    cursor: pointer;
    padding: 2px;
    border-radius: 4px;
    display: inline-flex;
    align-items: center;
    transition: opacity 0.15s ease, color 0.15s ease, background-color 0.15s ease;
}

.session-item:hover .session-delete,
.session-item.active .session-delete {
    opacity: 1;
}

.session-delete:hover:not(:disabled) {
    color: #f56c6c;
    background: rgba(245, 108, 108, 0.08);
}

.session-delete:disabled {
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

.send-btn .is-loading {
    animation: send-spin 0.8s linear infinite;
}

@keyframes send-spin {
    to {
        transform: rotate(360deg);
    }
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
