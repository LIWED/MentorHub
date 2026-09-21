<template>
  <div class="interview-chat-page">
    <!-- 阶段进度条 -->
    <StageProgressBar :current="currentStage" />

    <!-- 报告（面试结束后显示） -->
    <template v-if="isFinished && report">
      <div class="nm-card report-card">
        <div class="card-header">
          <div class="header-icon-box">
            <span class="header-icon">🎉</span>
          </div>
          <div>
            <h3 class="card-title">AI 模拟面试综合评估报告</h3>
            <p class="card-subtitle">目标应聘岗位：{{ report.target_position }}</p>
          </div>
        </div>

        <!-- 综合评分与总评 -->
        <div class="report-hero">
          <div class="hero-score-box">
            <span class="hero-score-num">{{ report.overall_score }}</span>
            <span class="hero-score-label">综合评分 (满分 100)</span>
          </div>
          <div class="hero-comment-box">
            <div class="comment-badge">面试官综合评语</div>
            <p class="comment-text">{{ report.overall_comment }}</p>
          </div>
        </div>

        <!-- 优势与待提升 -->
        <el-row :gutter="20" style="margin-bottom: 24px">
          <el-col :xs="24" :md="12">
            <div class="eval-box strengths">
              <div class="box-title">
                <span>✅ 面试亮点与核心优势</span>
              </div>
              <ul class="eval-list">
                <li v-for="(s, i) in report.strengths" :key="i">{{ s }}</li>
              </ul>
            </div>
          </el-col>
          <el-col :xs="24" :md="12">
            <div class="eval-box improvements">
              <div class="box-title">
                <span>🔧 关键知识薄弱与待提升</span>
              </div>
              <ul class="eval-list">
                <li v-for="(s, i) in report.improvements" :key="i">{{ s }}</li>
              </ul>
            </div>
          </el-col>
        </el-row>

        <!-- 建议学习方向与下一步 -->
        <el-row :gutter="20" style="margin-bottom: 24px">
          <el-col :xs="24" :md="12">
            <div class="advice-box">
              <div class="advice-title">📚 推荐攻坚学习方向</div>
              <div class="topic-tags">
                <span
                  v-for="(t, i) in report.recommended_topics"
                  :key="i"
                  class="topic-chip"
                >
                  {{ t }}
                </span>
              </div>
            </div>
          </el-col>
          <el-col :xs="24" :md="12">
            <div class="advice-box">
              <div class="advice-title">🚀 下一步面试提升建议</div>
              <p class="next-step-text">{{ report.next_step_advice }}</p>
            </div>
          </el-col>
        </el-row>

        <!-- 各维度评分明细 -->
        <div class="section-title">各考察维度明细评分</div>
        <el-row :gutter="16">
          <el-col
            v-for="dim in report.dimensions"
            :key="dim.dimension"
            :xs="24"
            :sm="12"
            :md="8"
            style="margin-bottom: 16px"
          >
            <div class="dimension-subcard">
              <div class="dim-sub-header">
                <span class="dim-sub-name">{{ dim.dimension }}</span>
                <span class="dim-sub-score">{{ dim.score }} 分</span>
              </div>
              <div class="dim-sub-track">
                <div class="dim-sub-fill" :style="{ width: `${dim.score}%` }" />
              </div>
              <div class="dim-sub-comment">{{ dim.comment }}</div>
            </div>
          </el-col>
        </el-row>

        <div class="report-actions">
          <button class="nm-button-primary back-list-btn" @click="router.push('/interview')">
            返回面试配置中心
          </button>
        </div>
      </div>
    </template>

    <!-- 聊天区（面试进行中） -->
    <template v-else>
      <div class="nm-card chat-card">
        <div class="chat-messages" ref="messagesEl">
          <ChatBubble
            v-for="(msg, i) in messages"
            :key="i"
            :role="msg.role"
          >
            <MarkdownRenderer :content="msg.content" />
          </ChatBubble>

          <ChatBubble v-if="restoringHistory && !messages.length" role="assistant">
            <div class="thinking">
              <div class="wave-dots">
                <span class="dot" /><span class="dot" /><span class="dot" />
              </div>
              <span class="stage-text">正在恢复上次面试记录...</span>
            </div>
          </ChatBubble>

          <ChatBubble v-if="sessionUnavailable && !messages.length" role="assistant">
            <MarkdownRenderer content="当前面试的运行状态已失效，请返回面试中心重新开始一次面试。" />
          </ChatBubble>

          <!-- 流式思考中/等待 -->
          <ChatBubble v-if="loading && !streamingReply" role="assistant">
            <div class="thinking">
              <div class="wave-dots">
                <span class="dot" /><span class="dot" /><span class="dot" />
              </div>
              <span class="stage-text">面试官正在思考与评估你的回答...</span>
            </div>
          </ChatBubble>
        </div>

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
              v-model="inputText"
              type="textarea"
              :style="{ '--custom-textarea-height': `${inputHeight}px` }"
              placeholder="请输入你的回答... Ctrl+Enter 发送"
              resize="none"
              :disabled="restoringHistory || sessionUnavailable || loading || isFinished"
              @keydown.ctrl.enter="sendMessage"
            />

            <div class="input-actions-bar">
              <div class="actions-left">
                <span class="turn-pill">
                  🎯 第 {{ totalTurns }} 轮对话
                </span>
                <span class="hint-key">支持 Ctrl+Enter 快捷发送</span>
              </div>

              <div class="actions-right">
                <button
                  type="button"
                  class="end-interview-btn"
                  :disabled="restoringHistory || sessionUnavailable || loading || isFinished"
                  @click="endInterview"
                >
                  结束面试
                </button>

                <button
                  type="button"
                  class="nm-send-btn"
                  :disabled="restoringHistory || sessionUnavailable || !inputText.trim() || isFinished || loading"
                  :class="{ 'is-loading': loading }"
                  @click="sendMessage"
                >
                  <span v-if="loading" class="send-spinner" />
                  <span v-else class="send-text">发 送</span>
                  <el-icon v-if="!loading" class="send-icon"><Position /></el-icon>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Position } from '@element-plus/icons-vue'
import ChatBubble from '@/components/chat/ChatBubble.vue'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import StageProgressBar from '@/components/interview/StageProgressBar.vue'
import { interviewApi, type InterviewReport } from '@/api/interview'
import { useResizableInput } from '@/composables/useResizableInput'
import client from '@/api/client'

// 可调节输入框上边界高度/宽度
const { inputHeight, isDraggingInput, handleResizeStart, resetInputHeight } = useResizableInput()

interface Message {
  role: 'user' | 'assistant'
  content: string
}

const route = useRoute()
const router = useRouter()
const sessionId = route.params.sessionId as string

const messages = ref<Message[]>([])
const inputText = ref('')
const loading = ref(false)
const streamingReply = ref(false)
const restoringHistory = ref(true)
const sessionUnavailable = ref(false)
const currentStage = ref('warmup')
const totalTurns = ref(0)
const isFinished = ref(false)
const report = ref<InterviewReport | null>(null)
const messagesEl = ref<HTMLElement>()

// ── 发送消息（流式） ──────────────────────────────────────────
async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || loading.value || restoringHistory.value || sessionUnavailable.value) return

  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  loading.value = true
  await scrollToBottom()

  let streamBubbleIndex = -1

  return new Promise<void>((resolve) => {
    interviewApi.chatStream(sessionId, text, {
      onToken: async (chunk) => {
        if (streamBubbleIndex === -1) {
          messages.value.push({ role: 'assistant', content: '' })
          streamBubbleIndex = messages.value.length - 1
          streamingReply.value = true
        }
        messages.value[streamBubbleIndex].content += chunk
        await scrollToBottom()
      },
      onDone: async (meta) => {
        streamingReply.value = false
        currentStage.value = meta.current_stage
        totalTurns.value = meta.total_turns

        if (streamBubbleIndex === -1) {
          if (meta.reply) {
            messages.value.push({ role: 'assistant', content: meta.reply })
            streamBubbleIndex = messages.value.length - 1
          }
        } else if (!messages.value[streamBubbleIndex]?.content && meta.reply) {
          messages.value[streamBubbleIndex].content = meta.reply
        }

        if (meta.is_finished) {
          isFinished.value = true
          await fetchReport()
        }

        loading.value = false
        await scrollToBottom()
        resolve()
      },
      onError: async () => {
        streamingReply.value = false
        if (streamBubbleIndex !== -1 && !messages.value[streamBubbleIndex]?.content) {
          messages.value.splice(streamBubbleIndex, 1)
        }
        ElMessage.error('发送失败，请重试')
        loading.value = false
        await scrollToBottom()
        resolve()
      },
    })
  })
}

async function endInterview() {
  inputText.value = '结束面试'
  await sendMessage()
}

async function fetchReport() {
  try {
    const res = await client.get(`/interview/sessions/${sessionId}/report`, {
      validateStatus: (s: number) => s < 500,
    })
    if (res.status === 200) report.value = res.data
  } catch {
    // ignore
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}

async function restoreSession() {
  restoringHistory.value = true
  try {
    const { data } = await interviewApi.getHistory(sessionId)
    sessionUnavailable.value = false
    messages.value = data.messages.map(msg => ({
      role: msg.role,
      content: msg.content,
    }))
    currentStage.value = data.current_stage
    totalTurns.value = data.total_turns

    if (data.status === 'finished' || data.current_stage === 'finished') {
      isFinished.value = true
      currentStage.value = 'finished'
      await fetchReport()
    }
  } catch (error: any) {
    // 新建会话时保留 history.state 作为短暂网络异常下的兜底；正常恢复以服务端 State 为准。
    const openingMessage = (history.state as any)?.openingMessage
    if (openingMessage) {
      messages.value = [{ role: 'assistant', content: openingMessage }]
    }

    if (error?.response?.status === 409) {
      // 409 已由 Axios 全局拦截器提示；这里仅切换页面状态，避免重复弹两条通知。
      sessionUnavailable.value = true
    } else if (!openingMessage) {
      ElMessage.error('加载面试记录失败，请返回列表后重试')
    }

    // 已完成会话不依赖运行时 MemorySaver，报告仍可直接从数据库恢复。
    await fetchReport()
    if (report.value) {
      isFinished.value = true
      currentStage.value = 'finished'
    }
  } finally {
    restoringHistory.value = false
    await scrollToBottom()
  }
}

onMounted(restoreSession)
</script>

<style scoped>
.interview-chat-page {
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
  animation: pop-in 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* 聊天卡片 */
.chat-card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  height: calc(100vh - 64px - 48px - 80px);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px;
}

/* 输入区 */
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

.turn-pill {
  font-size: 11.5px;
  color: var(--nm-text-secondary);
  background: rgba(255, 255, 255, 0.7);
  padding: 3px 10px;
  border-radius: var(--nm-radius-full);
  box-shadow: inset 1px 1px 2px rgba(166, 180, 200, 0.25);
  font-weight: 600;
}

.hint-key {
  font-size: 11.5px;
  color: var(--nm-text-light);
}

.actions-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.end-interview-btn {
  padding: 7px 14px;
  border-radius: var(--nm-radius-md);
  background: var(--nm-bg);
  border: 1px solid rgba(239, 68, 68, 0.3);
  box-shadow: var(--nm-shadow-sm);
  color: var(--nm-danger);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: var(--nm-transition);
}

.end-interview-btn:hover:not(:disabled) {
  background: #fee2e2;
  box-shadow: var(--nm-shadow-hover);
}

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

@keyframes spin { to { transform: rotate(360deg); } }

/* 思考波浪动画 */
.thinking {
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

/* 报告卡片 */
.report-card {
  padding: 28px 32px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 22px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(203, 213, 225, 0.4);
}

.header-icon-box {
  width: 44px;
  height: 44px;
  border-radius: var(--nm-radius-md);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-sm);
  border: var(--nm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.header-icon {
  font-size: 22px;
}

.card-title {
  margin: 0 0 4px;
  font-size: 17px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

.card-subtitle {
  margin: 0;
  font-size: 12.5px;
  color: var(--nm-text-secondary);
}

.report-hero {
  display: flex;
  align-items: center;
  gap: 32px;
  padding: 20px 24px;
  background: var(--nm-bg);
  border-radius: var(--nm-radius-lg);
  box-shadow: var(--nm-shadow-inset);
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.hero-score-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 16px 24px;
  background: var(--nm-bg);
  border-radius: var(--nm-radius-md);
  box-shadow: var(--nm-shadow-sm);
  border: var(--nm-border);
  flex-shrink: 0;
}

.hero-score-num {
  font-size: 46px;
  font-weight: 800;
  background: linear-gradient(135deg, #1e293b 0%, #3b82f6 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  line-height: 1;
}

.hero-score-label {
  font-size: 11px;
  color: var(--nm-text-light);
  margin-top: 4px;
}

.hero-comment-box {
  flex: 1;
  min-width: 260px;
}

.comment-badge {
  font-size: 11px;
  color: var(--nm-primary);
  background: rgba(59, 130, 246, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
  display: inline-block;
  margin-bottom: 6px;
}

.comment-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.65;
  color: var(--nm-text-regular);
}

.eval-box {
  padding: 18px 20px;
  border-radius: var(--nm-radius-lg);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-sm);
  border: var(--nm-border);
  height: 100%;
  box-sizing: border-box;
}

.eval-box.strengths { border-left: 4px solid var(--nm-success); }
.eval-box.improvements { border-left: 4px solid var(--nm-warning); }

.box-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--nm-text-primary);
  margin-bottom: 12px;
}

.eval-list {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.75;
  color: var(--nm-text-regular);
}

.advice-box {
  padding: 16px 20px;
  border-radius: var(--nm-radius-md);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-inset);
  height: 100%;
  box-sizing: border-box;
}

.advice-title {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--nm-text-primary);
  margin-bottom: 10px;
}

.topic-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.topic-chip {
  font-size: 12px;
  color: var(--nm-primary);
  background: var(--nm-bg);
  padding: 4px 10px;
  border-radius: var(--nm-radius-full);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
}

.next-step-text {
  margin: 0;
  font-size: 13px;
  color: var(--nm-text-regular);
  line-height: 1.6;
}

.section-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--nm-text-primary);
  margin: 16px 0 14px;
}

.dimension-subcard {
  padding: 14px 16px;
  border-radius: var(--nm-radius-md);
  background: var(--nm-bg);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
}

.dim-sub-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.dim-sub-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--nm-text-primary);
}

.dim-sub-score {
  font-size: 14px;
  font-weight: 700;
  color: var(--nm-primary);
}

.dim-sub-track {
  height: 6px;
  background: var(--nm-bg);
  border-radius: var(--nm-radius-full);
  box-shadow: var(--nm-shadow-inset);
  overflow: hidden;
  margin-bottom: 6px;
}

.dim-sub-fill {
  height: 100%;
  background: var(--nm-primary-gradient);
  border-radius: var(--nm-radius-full);
}

.dim-sub-comment {
  font-size: 11.5px;
  color: var(--nm-text-light);
  line-height: 1.4;
}

.report-actions {
  margin-top: 24px;
  display: flex;
  justify-content: flex-end;
}

.back-list-btn {
  padding: 10px 24px;
  font-size: 13.5px;
}
</style>
