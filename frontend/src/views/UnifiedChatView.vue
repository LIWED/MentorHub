<template>
  <div class="chat-page">
    <div class="chat-panel">
      <!-- 顶部功能说明栏 -->
      <div class="chat-header-hint">
        <div class="hint-icon-box">
          <el-icon><MagicStick /></el-icon>
        </div>
        <div class="hint-text">
          <span>AI 统一意图识别中心：输入任意学习或求职需求，系统将自动识别意图并调度最适合的 Agent</span>
        </div>
      </div>

      <!-- 消息区 -->
      <div class="chat-messages" ref="messagesEl">
        <div v-if="messages.length === 0 && !isStreaming" class="empty-hint">
          <div class="empty-sparkle-box">
            <img :src="iconAiHero" class="empty-sparkle-img" alt="AI Core" />
          </div>
          <h3 class="empty-title">您好！我是 MentorHub AI 统一管家</h3>
          <p class="empty-sub">支持单 Agent 直答与跨 Agent 复合流水线编排。请直接描述您的需求：</p>
          <div class="example-queries">
            <span
              v-for="q in exampleQueries"
              :key="q"
              class="example-chip"
              @click="sendExample(q)"
            >
              {{ q }} ↗
            </span>
          </div>
        </div>

        <template v-for="(msg, i) in messages" :key="i">
          <!-- 路由决策卡片（仅 assistant 消息有） -->
          <RoutingDecisionCard
            v-if="msg.routingDecision"
            :agent-type="msg.routingDecision.agent_type"
            :agent-display="msg.routingDecision.agent_display"
            :confidence="msg.routingDecision.confidence"
            :reason="msg.routingDecision.reason"
            :execution-mode="msg.routingDecision.execution_mode"
          />

          <!-- 多 Agent 协同管道计划卡片 -->
          <PipelinePlanCard
            v-if="msg.pipelinePlan"
            :title="msg.pipelinePlan.title"
            :intro="msg.pipelinePlan.intro"
            :steps="msg.pipelinePlan.steps"
          />

          <!-- 普通气泡（pipeline_plan 消息无需气泡） -->
          <ChatBubble v-if="!msg.pipelinePlan" :role="msg.role" :sources="msg.sources">
            <!-- 引导消息：带跳转按钮 -->
            <template v-if="msg.guidance">
              <p style="margin: 0 0 12px; font-size: 14.5px">{{ msg.guidance.message }}</p>
              <button
                v-if="msg.guidance.action_label"
                type="button"
                class="guidance-action-btn"
                @click="router.push(msg.guidance.action_url)"
              >
                <span>{{ msg.guidance.action_label }}</span>
                <el-icon><ArrowRight /></el-icon>
              </button>
            </template>
            <MarkdownRenderer v-else :content="msg.content" />
          </ChatBubble>
        </template>

        <!-- 流式气泡 -->
        <template v-if="isStreaming">
          <RoutingDecisionCard
            v-if="streamingRouting"
            :agent-type="streamingRouting.agent_type"
            :agent-display="streamingRouting.agent_display"
            :confidence="streamingRouting.confidence"
            :reason="streamingRouting.reason"
            :execution-mode="streamingRouting.execution_mode"
          />
          <ChatBubble role="assistant">
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
              <span class="stage-text">意图路由分析与调度中...</span>
            </div>
          </ChatBubble>
        </template>
      </div>

      <!-- 底部输入区 -->
      <div class="chat-input-container">
        <div class="input-sunken-well">
          <el-input
            ref="inputRef"
            v-model="inputText"
            type="textarea"
            :rows="3"
            placeholder="直接描述您的需求（例如：帮我审查简历并准备模拟面试），Enter 发送，Shift+Enter 换行"
            resize="none"
            :disabled="isStreaming"
            @keydown="handleKeydown"
          />
          <div class="input-actions-bar">
            <div class="actions-left">
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
import { ref, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { MagicStick, ArrowRight, Position } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import ChatBubble from '@/components/chat/ChatBubble.vue'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import RoutingDecisionCard from '@/components/chat/RoutingDecisionCard.vue'
import PipelinePlanCard from '@/components/chat/PipelinePlanCard.vue'
import iconAiHero from '@/assets/images/icon_ai_hero.svg'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

interface RoutingDecision {
  agent_type: string
  agent_display: string
  confidence: number
  reason: string
  execution_mode: string
}

interface GuidanceInfo {
  message: string
  action_label: string
  action_url: string
}

interface PipelineStep {
  step: number
  agent_type: string
  label: string
  desc: string
  action_label: string
  action_url: string
  tip: string
}

interface PipelinePlan {
  title: string
  intro: string
  steps: PipelineStep[]
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
  routingDecision?: RoutingDecision
  guidance?: GuidanceInfo
  pipelinePlan?: PipelinePlan
}

const messages = ref<Message[]>([])
const inputText = ref('')
const messagesEl = ref<HTMLElement>()
const sessionId = ref(`unified_${auth.user?.userId ?? 'guest'}`)

const isStreaming = ref(false)
const streamingText = ref('')
const streamingRouting = ref<RoutingDecision | null>(null)
const progressStage = ref('')
const lastAnswerMode = ref('')
const lastConfidence = ref(0)
const lastSources = ref<string[]>([])

const exampleQueries = [
  'Python 中的 GIL 是什么？',
  '我想提交试卷批改',
  '帮我审查一下简历',
  '我要开始模拟面试',
  '帮我准备求职全流程',
]

const answerModeLabel = computed(() => {
  const map: Record<string, string> = {
    rag: `RAG ${lastConfidence.value}%`,
    general: '通用回答',
    llm_direct: 'LLM直答',
  }
  return map[lastAnswerMode.value] ?? lastAnswerMode.value
})

function sendExample(q: string) {
  inputText.value = q
  sendMessage()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.isComposing) return
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return

  inputText.value = ''
  messages.value.push({ role: 'user', content: text })
  await scrollToBottom()

  isStreaming.value = true
  streamingText.value = ''
  streamingRouting.value = null
  progressStage.value = ''
  lastAnswerMode.value = ''
  lastSources.value = []

  let pendingRouting: RoutingDecision | null = null
  let pendingGuidance: GuidanceInfo | null = null
  let pendingPipelinePlan: PipelinePlan | null = null

  try {
    const apiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'
    const resp = await fetch(`${apiBase}/api/v1/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${auth.token}`,
      },
      body: JSON.stringify({
        session_id: sessionId.value,
        message: text,
      }),
    })

    if (resp.status === 401) {
      auth.logout()
      router.push('/login')
      return
    }
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)

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

          if (evt.type === 'routing_decision') {
            pendingRouting = {
              agent_type:     evt.agent_type,
              agent_display:  evt.agent_display,
              confidence:     evt.confidence,
              reason:         evt.reason,
              execution_mode: evt.execution_mode,
            }
            streamingRouting.value = pendingRouting
            await scrollToBottom()

          } else if (evt.type === 'progress') {
            progressStage.value = evt.stage

          } else if (evt.type === 'token') {
            progressStage.value = ''
            streamingText.value += evt.content
            await scrollToBottom()

          } else if (evt.type === 'guidance') {
            pendingGuidance = {
              message:      evt.message,
              action_label: evt.action_label ?? '',
              action_url:   evt.action_url ?? '',
            }

          } else if (evt.type === 'pipeline_plan') {
            pendingPipelinePlan = {
              title: evt.title,
              intro: evt.intro,
              steps: evt.steps ?? [],
            }
            await scrollToBottom()

          } else if (evt.type === 'meta') {
            lastAnswerMode.value = evt.answer_mode ?? ''
            lastConfidence.value = Math.round((evt.confidence ?? 0) * 100)
            lastSources.value    = evt.sources ?? []

          } else if (evt.type === 'error') {
            throw new Error(evt.message ?? 'SSE error')
          }
        } catch {
          // 忽略非 JSON 行
        }
      }
    }

    // 流结束：将流式内容固化为消息
    if (pendingPipelinePlan) {
      messages.value.push({
        role:            'assistant',
        content:         '',
        routingDecision: pendingRouting ?? undefined,
        pipelinePlan:    pendingPipelinePlan,
      })
    } else if (pendingGuidance) {
      messages.value.push({
        role:            'assistant',
        content:         pendingGuidance.message,
        routingDecision: pendingRouting ?? undefined,
        guidance:        pendingGuidance,
      })
    } else if (streamingText.value) {
      messages.value.push({
        role:            'assistant',
        content:         streamingText.value,
        sources:         lastSources.value,
        routingDecision: pendingRouting ?? undefined,
      })
    }

  } catch (err) {
    ElMessage.error('请求失败，请重试')
    console.error('[UnifiedChat SSE]', err)
  } finally {
    isStreaming.value = false
    streamingText.value = ''
    streamingRouting.value = null
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
</script>

<style scoped>
.chat-page {
  display: flex;
  height: calc(100vh - 64px - 48px);
}

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

.chat-header-hint {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 24px;
  border-bottom: 1px solid rgba(203, 213, 225, 0.4);
  background: rgba(255, 255, 255, 0.4);
}

.hint-icon-box {
  width: 28px;
  height: 28px;
  border-radius: var(--nm-radius-sm);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-sm);
  border: var(--nm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--nm-primary);
  font-size: 15px;
}

.hint-text {
  font-size: 12.5px;
  color: var(--nm-text-secondary);
  font-weight: 500;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px;
}

.empty-hint {
  text-align: center;
  max-width: 560px;
  margin: 50px auto 0;
  animation: pop-in 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.empty-sparkle-box {
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
}

.empty-sparkle-img {
  width: 48px;
  height: 48px;
  object-fit: contain;
  animation: float-gentle 3.5s ease-in-out infinite;
}

.empty-title {
  margin: 0 0 8px;
  font-size: 19px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

.empty-sub {
  margin: 0 0 20px;
  font-size: 13.5px;
  color: var(--nm-text-secondary);
  line-height: 1.6;
}

.example-queries {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}

.example-chip {
  padding: 7px 14px;
  background: var(--nm-bg);
  border: var(--nm-border);
  border-radius: var(--nm-radius-full);
  box-shadow: var(--nm-shadow-sm);
  color: var(--nm-text-regular);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: var(--nm-transition);
}

.example-chip:hover {
  transform: translateY(-2px) scale(1.02);
  color: var(--nm-primary);
  box-shadow: var(--nm-shadow-hover);
}

.example-chip:active {
  transform: translateY(1px);
  box-shadow: var(--nm-shadow-pressed);
}

.guidance-action-btn {
  padding: 8px 16px;
  border-radius: var(--nm-radius-md);
  background: var(--nm-primary-gradient);
  border: none;
  color: #ffffff;
  font-size: 13px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.35);
  transition: var(--nm-transition);
}

.guidance-action-btn:hover {
  transform: translateY(-2px) scale(1.02);
  box-shadow: 0 6px 16px rgba(59, 130, 246, 0.45);
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
  transition: var(--nm-transition-smooth);
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
}

.input-actions-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(203, 213, 225, 0.3);
}

.mode-tag-pill {
  font-size: 11.5px;
  padding: 3px 9px;
  border-radius: var(--nm-radius-full);
  font-weight: 600;
}

.mode-tag-pill.rag { background: #dcfce7; color: #059669; }
.mode-tag-pill.general { background: #fef3c7; color: #d97706; }
.mode-tag-pill.llm_direct { background: #e0f2fe; color: #0284c7; }

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
