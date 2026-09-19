<template>
  <div class="pipeline-card">
    <!-- 标题栏 -->
    <div class="pipeline-header">
      <div class="pipeline-icon-box">
        <el-icon><Share /></el-icon>
      </div>
      <span class="pipeline-title">{{ title }}</span>
      <span class="pipeline-badge">多 Agent 协同流</span>
    </div>

    <!-- 简介 -->
    <p class="pipeline-intro">{{ intro }}</p>

    <!-- 步骤列表 -->
    <div class="pipeline-steps">
      <div
        v-for="(step, index) in steps"
        :key="step.step"
        class="step-wrapper"
      >
        <!-- 步骤卡片 -->
        <div class="step-card" @click="router.push(step.action_url)">
          <div class="step-left">
            <div class="step-badge" :class="`step-badge--${step.agent_type}`">
              <img v-if="agentIcon[step.agent_type]" :src="agentIcon[step.agent_type]" class="step-icon-img" :alt="step.label" />
              <span v-else>🤖</span>
            </div>
            <div class="step-info">
              <div class="step-label">
                <span class="step-num">Step {{ step.step }}</span>
                <span class="step-name">{{ step.label }}</span>
              </div>
              <div class="step-desc">{{ step.desc }}</div>
              <div class="step-tip">
                <el-icon><InfoFilled /></el-icon>
                <span>{{ step.tip }}</span>
              </div>
            </div>
          </div>
          <button class="step-action-btn" type="button">
            <span>{{ step.action_label }}</span>
            <el-icon><ArrowRight /></el-icon>
          </button>
        </div>

        <!-- 步骤间连接箭头 -->
        <div v-if="index < steps.length - 1" class="step-connector">
          <div class="connector-line" />
          <div class="connector-dot">
            <el-icon><ArrowDown /></el-icon>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { Share, InfoFilled, ArrowDown, ArrowRight } from '@element-plus/icons-vue'
import iconQa from '@/assets/images/icon_qa.jpg'
import iconExam from '@/assets/images/icon_exam.jpg'
import iconResume from '@/assets/images/icon_resume.jpg'
import iconInterview from '@/assets/images/icon_interview.svg'

defineProps<{
  title: string
  intro: string
  steps: Array<{
    step: number
    agent_type: string
    label: string
    desc: string
    action_label: string
    action_url: string
    tip: string
  }>
}>()

const router = useRouter()

const agentIcon: Record<string, string> = {
  resume:    iconResume,
  interview: iconInterview,
  exam:      iconExam,
  qa:        iconQa,
}
</script>

<style scoped>
.pipeline-card {
  background: var(--nm-bg);
  border: var(--nm-border);
  border-radius: var(--nm-radius-lg);
  box-shadow: var(--nm-shadow-flat);
  padding: 18px 20px;
  margin-bottom: 14px;
  animation: pop-in 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.pipeline-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.pipeline-icon-box {
  width: 32px;
  height: 32px;
  border-radius: var(--nm-radius-sm);
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #b45309;
  box-shadow: var(--nm-shadow-sm);
}

.pipeline-title {
  flex: 1;
  font-size: 15px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

.pipeline-badge {
  font-size: 11px;
  font-weight: 600;
  color: #b45309;
  background: #fef3c7;
  padding: 3px 9px;
  border-radius: var(--nm-radius-full);
  box-shadow: inset 1px 1px 2px rgba(180, 83, 9, 0.2);
}

.pipeline-intro {
  margin: 0 0 16px;
  color: var(--nm-text-regular);
  line-height: 1.6;
  font-size: 13px;
}

.pipeline-steps {
  display: flex;
  flex-direction: column;
}

.step-wrapper {
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

.step-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--nm-bg);
  border: var(--nm-border);
  border-radius: var(--nm-radius-md);
  box-shadow: var(--nm-shadow-sm);
  padding: 12px 16px;
  gap: 14px;
  cursor: pointer;
  transition: var(--nm-transition);
}

.step-card:hover {
  transform: translateY(-2px) scale(1.008);
  box-shadow: var(--nm-shadow-hover);
}

.step-card:hover .step-action-btn {
  background: var(--nm-primary);
  color: #ffffff;
  box-shadow: 0 4px 10px rgba(59, 130, 246, 0.35);
}

.step-left {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex: 1;
}

.step-badge {
  width: 40px;
  height: 40px;
  border-radius: var(--nm-radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
  box-shadow: 2px 2px 6px rgba(166, 180, 200, 0.3);
}

.step-icon-img {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  object-fit: cover;
}

.step-badge--resume    { background: linear-gradient(135deg, #e0f2fe 0%, #bae6fd 100%); }
.step-badge--interview { background: linear-gradient(135deg, #fce7f3 0%, #fbcfe8 100%); }
.step-badge--exam      { background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); }
.step-badge--qa        { background: linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%); }

.step-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1;
}

.step-label {
  display: flex;
  align-items: center;
  gap: 8px;
}

.step-num {
  font-size: 11px;
  font-weight: 700;
  color: var(--nm-primary);
  background: rgba(59, 130, 246, 0.1);
  padding: 1px 6px;
  border-radius: 4px;
}

.step-name {
  font-weight: 700;
  color: var(--nm-text-primary);
  font-size: 13.5px;
}

.step-desc {
  color: var(--nm-text-secondary);
  font-size: 12.5px;
  line-height: 1.5;
}

.step-tip {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #b45309;
  font-size: 11.5px;
  margin-top: 2px;
}

.step-action-btn {
  flex-shrink: 0;
  padding: 6px 14px;
  border-radius: var(--nm-radius-full);
  background: var(--nm-bg);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
  color: var(--nm-primary);
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  transition: var(--nm-transition);
}

.step-connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 4px 0;
  position: relative;
}

.connector-line {
  width: 2px;
  height: 12px;
  background: #cbd5e1;
}

.connector-dot {
  font-size: 13px;
  color: #94a3b8;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
