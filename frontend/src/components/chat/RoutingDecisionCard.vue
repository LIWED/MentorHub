<template>
  <div class="routing-card">
    <div class="routing-header">
      <div class="icon-chip">
        <el-icon class="routing-icon"><Connection /></el-icon>
      </div>
      <span class="routing-title">意图路由决策</span>
      <div class="confidence-pill" :class="confidenceTagType">
        <span class="confidence-dot" />
        <span>{{ Math.round(confidence * 100) }}% 置信度</span>
      </div>
    </div>

    <div class="routing-body">
      <div class="routing-row">
        <span class="label">目标 Agent</span>
        <div class="agent-chip" :class="agentType">
          <img v-if="agentIcon[agentType]" :src="agentIcon[agentType]" class="agent-thumb-img" :alt="agentDisplay" />
          <span v-else class="agent-icon">🤖</span>
          <span class="agent-name">{{ agentDisplay }}</span>
        </div>
      </div>

      <div class="routing-row">
        <span class="label">执行模式</span>
        <span class="mode-badge" :class="executionMode">{{ modeDisplay }}</span>
      </div>

      <div class="routing-row">
        <span class="label">判定依据</span>
        <span class="reason-text">{{ reason }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Connection } from '@element-plus/icons-vue'
import iconQa from '@/assets/images/icon_qa.jpg'
import iconExam from '@/assets/images/icon_exam.jpg'
import iconResume from '@/assets/images/icon_resume.jpg'
import iconInterview from '@/assets/images/icon_interview.svg'

const props = defineProps<{
  agentType: string
  agentDisplay: string
  confidence: number
  reason: string
  executionMode: string
}>()

const agentIcon: Record<string, string> = {
  qa: iconQa,
  exam: iconExam,
  resume: iconResume,
  interview: iconInterview,
}

const confidenceTagType = computed(() => {
  if (props.confidence >= 0.85) return 'high'
  if (props.confidence >= 0.65) return 'medium'
  return 'low'
})

const modeDisplay = computed(() => {
  const map: Record<string, string> = {
    single:   '单 Agent 直达',
    pipeline: '多 Agent 协同链',
    clarify:  '待用户澄清',
  }
  return map[props.executionMode] ?? props.executionMode
})
</script>

<style scoped>
.routing-card {
  background: var(--nm-bg);
  border: var(--nm-border);
  border-radius: var(--nm-radius-lg);
  box-shadow: var(--nm-shadow-flat);
  padding: 14px 18px;
  margin-bottom: 14px;
  animation: pop-in 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.routing-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(203, 213, 225, 0.4);
}

.icon-chip {
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

.routing-title {
  flex: 1;
  font-size: 14px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

.confidence-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: var(--nm-radius-full);
  font-size: 11px;
  font-weight: 600;
  background: var(--nm-bg);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
}

.confidence-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.confidence-pill.high {
  color: var(--nm-success);
}
.confidence-pill.high .confidence-dot {
  background: var(--nm-success);
  box-shadow: 0 0 6px var(--nm-success);
}

.confidence-pill.medium {
  color: var(--nm-warning);
}
.confidence-pill.medium .confidence-dot {
  background: var(--nm-warning);
  box-shadow: 0 0 6px var(--nm-warning);
}

.confidence-pill.low {
  color: var(--nm-danger);
}
.confidence-pill.low .confidence-dot {
  background: var(--nm-danger);
  box-shadow: 0 0 6px var(--nm-danger);
}

.routing-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.routing-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.label {
  font-size: 12px;
  color: var(--nm-text-light);
  min-width: 65px;
  flex-shrink: 0;
  font-weight: 500;
}

.agent-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: var(--nm-radius-full);
  background: var(--nm-bg);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
  font-size: 12.5px;
  font-weight: 600;
  color: var(--nm-text-primary);
}

.agent-thumb-img {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  object-fit: cover;
}

.agent-chip.qa { color: #0284c7; }
.agent-chip.exam { color: #d97706; }
.agent-chip.resume { color: #059669; }
.agent-chip.interview { color: #db2777; }

.mode-badge {
  font-size: 12px;
  font-weight: 600;
  color: var(--nm-primary);
  background: rgba(59, 130, 246, 0.08);
  padding: 2px 8px;
  border-radius: 4px;
}

.reason-text {
  font-size: 13px;
  color: var(--nm-text-regular);
  line-height: 1.5;
}
</style>
