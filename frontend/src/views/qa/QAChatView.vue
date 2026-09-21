<template>
  <div class="qa-page">
    <!-- 左侧：会话列表 -->
    <div class="session-panel">
      <div class="session-header">
        <div class="session-title-box">
          <span class="session-icon">💬</span>
          <span class="session-title">问答会话</span>
        </div>
        <button class="nm-add-btn" title="新建会话" @click="newSession">
          <el-icon><Plus /></el-icon>
        </button>
      </div>

      <div class="session-list">
        <div
          v-for="s in sessions"
          :key="s.id"
          class="session-item"
          :class="{ active: s.id === currentSessionId }"
          @click="switchSession(s.id)"
        >
          <div class="session-item-icon">
            <el-icon><ChatDotRound /></el-icon>
          </div>
          <span class="session-name">{{ s.name }}</span>
          <button class="delete-btn" title="删除会话" @click.stop="deleteSession(s.id)">
            <el-icon><Close /></el-icon>
          </button>
        </div>
      </div>
    </div>

    <!-- 右侧：聊天区 -->
    <div class="chat-panel">
      <div class="chat-messages" ref="messagesEl">
        <div v-if="messages.length === 0 && !isStreaming" class="empty-hint">
          <div class="empty-icon-well">
            <img :src="iconQa" class="empty-icon-img" alt="QA Tutor" />
          </div>
          <h3 class="empty-title">你好！我是 MentorHub 智能导师</h3>
          <p class="empty-sub">支持基于专业 IT 知识库的 RAG 检索问答，与可选 Web 互联网实时扩展。</p>
          <div class="quick-questions">
            <span
              v-for="q in quickQuestions"
              :key="q"
              class="quick-pill"
              @click="sendQuickQuestion(q)"
            >
              {{ q }} →
            </span>
          </div>
        </div>

        <ChatBubble
          v-for="(msg, i) in messages"
          :key="i"
          :role="msg.role"
          :sources="msg.sources"
        >
          <MarkdownRenderer :content="msg.content" />
        </ChatBubble>

        <!-- 流式气泡：isStreaming 期间始终显示 -->
        <ChatBubble v-if="isStreaming" role="assistant">
          <template v-if="streamingText">
            <MarkdownRenderer :content="streamingText" />
          </template>
          <div v-else-if="progressStage" class="progress-hint">
            <div class="wave-dots">
              <span class="dot" /><span class="dot" /><span class="dot" />
            </div>
            <span class="stage-text">{{ progressStage }}</span>
          </div>
          <div v-else class="thinking">
            <div class="wave-dots">
              <span class="dot" /><span class="dot" /><span class="dot" />
            </div>
            <span class="stage-text">AI 正在检索与组织语言...</span>
          </div>
        </ChatBubble>
      </div>

      <!-- 底部输入区 -->
      <div class="chat-input-container" :class="{ 'is-resizing': isDraggingInput }">
        <!-- 顶部拖拽调整把手 (上边界) -->
        <div
          class="input-resize-handle"
          :class="{ 'is-dragging': isDraggingInput }"
          title="上下拉动上边界可调整输入框宽度/高度，双击恢复默认"
          @mousedown="handleResizeStart"
          @dblclick="resetInputHeight"
        >
          <span class="resize-bar" />
        </div>

        <div class="input-sunken-well">
          <el-input
            ref="inputRef"
            v-model="inputText"
            type="textarea"
            :style="{ '--custom-textarea-height': `${inputHeight}px` }"
            placeholder="输入你的技术问题... Enter 发送，Shift+Enter 换行"
            resize="none"
            :disabled="isStreaming"
            @keydown="handleKeydown"
          />
          <div class="input-actions-bar">
            <div class="actions-left">
              <!-- Web Search 开关 -->
              <el-tooltip
                :content="webSearchEnabled ? 'Web 搜索已开启：知识库未命中时将自动检索互联网' : 'Web 搜索已关闭：仅使用本地知识库与模型自有知识'"
                placement="top"
              >
                <div class="search-toggle-pill" :class="{ active: webSearchEnabled }">
                  <el-switch
                    v-model="webSearchEnabled"
                    :disabled="isStreaming"
                    size="small"
                  />
                  <span class="toggle-label">🌐 Web 联网增强</span>
                </div>
              </el-tooltip>

              <!-- 模式徽章 -->
              <span v-if="lastAnswerMode" class="mode-tag-pill" :class="lastAnswerMode">
                {{ answerModeLabel }}
              </span>
            </div>

            <div class="actions-right">
              <button
                class="nm-send-btn"
                :disabled="!inputText.trim() || isStreaming"
                :class="{ 'is-loading': isStreaming }"
                @click="sendMessage"
              >
                <span v-if="isStreaming" class="send-spinner" />
                <span v-else class="send-text">发 送</span>
                <el-icon v-if="!isStreaming" class="send-icon"><Position /></el-icon>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, ChatDotRound, Close, Position } from '@element-plus/icons-vue'
import { v4 as uuidv4 } from 'uuid'
import { ElMessage } from 'element-plus'
import ChatBubble from '@/components/chat/ChatBubble.vue'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import { useAuthStore } from '@/stores/auth'
import { qaApi } from '@/api/qa'
import { useResizableInput } from '@/composables/useResizableInput'
import iconQa from '@/assets/images/icon_qa.jpg'

// 明确声明组件名，保证 AppLayout 中的 keep-alive 能准确命中
defineOptions({ name: 'QAChatView' })

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'

// 可调节输入框上边界高度/宽度
const { inputHeight, isDraggingInput, handleResizeStart, resetInputHeight } = useResizableInput()

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
}

interface Session {
  id: string
  name: string
  messages: Message[]
  loaded?: boolean
}

const router = useRouter()
const auth = useAuthStore()

const sessions = ref<Session[]>([])
const currentSessionId = ref('')
const messages = ref<Message[]>([])
const inputText = ref('')
const messagesEl = ref<HTMLElement>()

// 流式状态
const isStreaming = ref(false)
const streamingText = ref('')
const progressStage = ref('')
const lastAnswerMode = ref('')
const lastConfidence = ref(0)
const lastSources = ref<string[]>([])

// Web Search 开关
const webSearchEnabled = ref(true)

const quickQuestions = [
  'TCP 三次握手与四次挥手过程是怎样的？',
  'Vue 3 的响应式原理与 Vue 2 有何不同？',
  'Redis 缓存穿透、击穿与雪崩如何应对？',
]

const answerModeLabel = computed(() => {
  switch (lastAnswerMode.value) {
    case 'rag':           return `RAG ${lastConfidence.value}%`
    case 'web_augmented': return `🌐 Web 增强`
    case 'general':       return '通用回答'
    default:              return 'LLM 直答'
  }
})

function sendQuickQuestion(q: string) {
  inputText.value = q
  sendMessage()
}

// ── 会话管理 ──────────────────────────────────────────────────
function newSession() {
  const id = `student_session_${uuidv4()}`
  const session: Session = { id, name: `新会话 ${sessions.value.length + 1}`, messages: [], loaded: true }
  sessions.value.unshift(session)
  switchSession(id)
}

async function switchSession(id: string) {
  if (isStreaming.value) return
  currentSessionId.value = id
  const s = sessions.value.find(s => s.id === id)
  if (!s) {
    messages.value = []
    return
  }

  if (!s.loaded) {
    try {
      const { data } = await qaApi.getHistory(id)
      s.messages = data.messages.map(m => ({
        role: m.role,
        content: m.content,
        sources: m.sources ?? [],
      }))
      s.loaded = true
    } catch (err) {
      ElMessage.error('加载历史会话失败')
      console.error('[QA history]', err)
    }
  }

  messages.value = s.messages
  await scrollToBottom()
}

async function deleteSession(id: string) {
  const idx = sessions.value.findIndex(s => s.id === id)
  if (idx === -1) return

  try {
    await qaApi.deleteSession(id)
  } catch (err: any) {
    if (err?.response?.status !== 404) {
      ElMessage.error('删除会话失败')
      return
    }
  }

  sessions.value.splice(idx, 1)
  if (currentSessionId.value === id) {
    if (sessions.value.length > 0) await switchSession(sessions.value[0].id)
    else newSession()
  }
}

// ── 键盘处理 ──────────────────────────────────────────────────
function handleKeydown(e: KeyboardEvent) {
  if (e.isComposing) return
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

// ── 发送消息（SSE） ──────────────────────────────────────────
async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return

  if (!currentSessionId.value) newSession()
  inputText.value = ''

  const session = sessions.value.find(s => s.id === currentSessionId.value)
  const userMsg: Message = { role: 'user', content: text }
  messages.value.push(userMsg)

  if (session && session.messages.filter(m => m.role === 'user').length === 1) {
    session.name = text.slice(0, 18) + (text.length > 18 ? '…' : '')
  }

  await scrollToBottom()

  isStreaming.value = true
  streamingText.value = ''
  progressStage.value = ''
  lastAnswerMode.value = ''
  lastSources.value = []

  try {
    const resp = await fetch(`${API_BASE}/api/v1/qa/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${auth.token}`,
      },
      body: JSON.stringify({
        session_id:        currentSessionId.value,
        message:           text,
        enable_web_search: webSearchEnabled.value,
      }),
    })

    if (resp.status === 401) {
      auth.logout()
      router.push('/login')
      return
    }
    if (!resp.ok || !resp.body) {
      throw new Error(`HTTP ${resp.status}`)
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''

      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        const raw = line.slice(5).trim()
        if (!raw) continue
        try {
          const evt = JSON.parse(raw)
          if (evt.type === 'progress' && evt.stage) {
            progressStage.value = evt.stage
          } else if (evt.type === 'token' && evt.content) {
            progressStage.value = ''
            streamingText.value += evt.content
            await scrollToBottom()
          } else if (evt.type === 'meta') {
            lastAnswerMode.value = evt.answer_mode ?? ''
            lastConfidence.value = Math.round((evt.confidence ?? 0) * 100)
            lastSources.value = evt.sources ?? []
          } else if (evt.type === 'error') {
            throw new Error(evt.message ?? 'SSE error')
          }
        } catch {
          // 忽略非 JSON 行
        }
      }
    }

    if (streamingText.value) {
      const assistantMsg: Message = {
        role: 'assistant',
        content: streamingText.value,
        sources: lastSources.value,
      }
      messages.value.push(assistantMsg)
    }

  } catch (err) {
    ElMessage.error('请求失败，请重试')
    console.error('[QA SSE]', err)
  } finally {
    isStreaming.value = false
    streamingText.value = ''
    progressStage.value = ''
    await scrollToBottom()
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}

async function loadSessions() {
  try {
    const { data } = await qaApi.listSessions()
    sessions.value = data.items.map(item => ({
      id: item.session_id,
      name: item.title || '新会话',
      messages: [],
      loaded: false,
    }))

    if (sessions.value.length > 0) {
      await switchSession(sessions.value[0].id)
    } else {
      newSession()
    }
  } catch (err) {
    console.error('[QA sessions]', err)
    newSession()
  }
}

onMounted(async () => {
  await loadSessions()
})
</script>

<style scoped>
.qa-page {
  display: flex;
  height: calc(100vh - 64px - 48px);
  gap: 18px;
}

/* ── 左侧会话列表 ── */
.session-panel {
  width: 240px;
  background: var(--nm-bg);
  border-radius: var(--nm-radius-lg);
  box-shadow: var(--nm-shadow-flat);
  border: var(--nm-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

.session-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid rgba(203, 213, 225, 0.4);
}

.session-title-box {
  display: flex;
  align-items: center;
  gap: 8px;
}

.session-icon {
  font-size: 16px;
}

.session-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

.nm-add-btn {
  width: 32px;
  height: 32px;
  border-radius: var(--nm-radius-sm);
  background: var(--nm-bg);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
  color: var(--nm-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: var(--nm-transition);
}

.nm-add-btn:hover {
  transform: scale(1.08);
  box-shadow: var(--nm-shadow-hover);
}

.nm-add-btn:active {
  transform: translateY(1px);
  box-shadow: var(--nm-shadow-pressed);
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 10px 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--nm-radius-md);
  cursor: pointer;
  font-size: 13px;
  color: var(--nm-text-regular);
  background: var(--nm-bg);
  border: 1px solid transparent;
  transition: var(--nm-transition);
}

.session-item:hover {
  color: var(--nm-primary);
  box-shadow: var(--nm-shadow-sm);
  border: var(--nm-border);
  transform: translateX(2px);
}

/* 激活态：凹陷槽 */
.session-item.active {
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-inset) !important;
  color: var(--nm-primary) !important;
  font-weight: 600;
  border: 1px solid rgba(255, 255, 255, 0.4) !important;
  transform: none !important;
}

.session-item-icon {
  display: flex;
  align-items: center;
  font-size: 15px;
  flex-shrink: 0;
}

.session-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.delete-btn {
  opacity: 0;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--nm-text-light);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  border-radius: 4px;
  transition: var(--nm-transition);
}

.session-item:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  color: var(--nm-danger) !important;
  transform: rotate(90deg);
}

/* ── 右侧聊天区 ── */
.chat-panel {
  flex: 1;
  background: var(--nm-bg);
  border-radius: var(--nm-radius-xl);
  box-shadow: var(--nm-shadow-flat);
  border: var(--nm-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px;
}

.empty-hint {
  text-align: center;
  max-width: 520px;
  margin: 60px auto 0;
  animation: pop-in 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.empty-icon-well {
  width: 72px;
  height: 72px;
  border-radius: var(--nm-radius-xl);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-flat);
  border: var(--nm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
  overflow: hidden;
}

.empty-icon-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  animation: float-gentle 3.5s ease-in-out infinite;
}

.empty-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

.empty-sub {
  margin: 0 0 20px;
  font-size: 13.5px;
  color: var(--nm-text-secondary);
  line-height: 1.6;
}

.quick-questions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.quick-pill {
  padding: 8px 14px;
  background: var(--nm-bg);
  border: var(--nm-border);
  border-radius: var(--nm-radius-md);
  box-shadow: var(--nm-shadow-sm);
  color: var(--nm-text-regular);
  font-size: 12.5px;
  cursor: pointer;
  transition: var(--nm-transition);
  text-align: left;
}

.quick-pill:hover {
  transform: translateX(4px);
  color: var(--nm-primary);
  box-shadow: var(--nm-shadow-hover);
}

/* 底部输入区 */
.chat-input-container {
  padding: 16px 20px 20px;
  background: var(--nm-bg);
  border-top: 1px solid rgba(203, 213, 225, 0.4);
}

.input-sunken-well {
  background: var(--nm-bg);
  border-radius: var(--nm-radius-lg);
  box-shadow: var(--nm-shadow-inset);
  border: 1px solid rgba(255, 255, 255, 0.4);
  padding: 10px 14px 8px;
  transition: box-shadow var(--nm-transition), border-color var(--nm-transition);
}

.input-sunken-well:focus-within {
  box-shadow: inset 4px 4px 8px rgba(166, 180, 200, 0.65), inset -4px -4px 8px rgba(255, 255, 255, 0.95), 0 0 0 2px rgba(59, 130, 246, 0.3);
}

.input-sunken-well :deep(.el-textarea__inner) {
  background: transparent !important;
  box-shadow: none !important;
  border: none !important;
  padding: 4px 0 !important;
  font-size: 14px;
  line-height: 1.6;
  height: var(--custom-textarea-height, 76px) !important;
  min-height: 54px;
  max-height: 500px;
  overflow-y: auto;
  resize: none !important;
  transition: none !important;
}

.input-actions-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(203, 213, 225, 0.3);
}

.actions-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-toggle-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: var(--nm-bg);
  border: var(--nm-border);
  border-radius: var(--nm-radius-full);
  box-shadow: var(--nm-shadow-sm);
  font-size: 12px;
  color: var(--nm-text-secondary);
}

.search-toggle-pill.active {
  color: var(--nm-primary);
  font-weight: 600;
}

.mode-tag-pill {
  font-size: 11.5px;
  padding: 3px 9px;
  border-radius: var(--nm-radius-full);
  font-weight: 600;
}

.mode-tag-pill.rag { background: #dcfce7; color: #059669; }
.mode-tag-pill.web_augmented { background: #e0f2fe; color: #0284c7; }
.mode-tag-pill.general { background: #fef3c7; color: #d97706; }

.nm-send-btn {
  padding: 8px 18px;
  background: var(--nm-primary-gradient);
  border: none;
  border-radius: var(--nm-radius-md);
  color: #ffffff;
  font-size: 13.5px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.35);
  transition: var(--nm-transition);
}

.nm-send-btn:hover:not(:disabled) {
  transform: translateY(-2px) scale(1.02);
  box-shadow: 0 6px 18px rgba(59, 130, 246, 0.45);
}

.nm-send-btn:active:not(:disabled) {
  transform: translateY(1px) scale(0.98);
}

.nm-send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  box-shadow: none;
}

.send-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── 思考与进度波浪动效 ── */
.thinking, .progress-hint {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0;
}

.wave-dots {
  display: flex;
  align-items: center;
  gap: 4px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--nm-primary);
  animation: bounce-wave 1.2s infinite ease-in-out;
}

.dot:nth-child(2) { animation-delay: 0.15s; }
.dot:nth-child(3) { animation-delay: 0.3s; }

.stage-text {
  font-size: 13px;
  color: var(--nm-text-secondary);
}
</style>
