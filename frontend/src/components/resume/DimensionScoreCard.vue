<template>
  <div class="nm-card dimension-card">
    <div class="dim-header">
      <span class="dim-name">{{ dimension }}</span>
      <div class="dim-score-box">
        <span class="score-val" :class="scoreClass">{{ score }}</span>
        <span class="score-max">/100</span>
      </div>
    </div>

    <!-- 拟物凹槽进度条 -->
    <div class="nm-progress-track">
      <div
        class="nm-progress-fill"
        :class="scoreClass"
        :style="{ width: `${Math.min(100, Math.max(0, score))}%` }"
      />
    </div>

    <div class="dim-weight-row">
      <span class="weight-chip">评估权重 {{ (weight * 100).toFixed(0) }}%</span>
    </div>

    <!-- 待解决问题 -->
    <div v-if="issues.length" class="feedback-group issues">
      <div v-for="(issue, i) in issues" :key="i" class="feedback-item">
        <div class="item-icon issue-icon">
          <el-icon><Warning /></el-icon>
        </div>
        <span class="item-text">{{ issue }}</span>
      </div>
    </div>

    <!-- 改进建议 -->
    <div v-if="suggestions.length" class="feedback-group suggestions">
      <div v-for="(s, i) in suggestions" :key="i" class="feedback-item">
        <div class="item-icon suggest-icon">
          <el-icon><CircleCheck /></el-icon>
        </div>
        <span class="item-text">{{ s }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Warning, CircleCheck } from '@element-plus/icons-vue'

const props = defineProps<{
  dimension: string
  score: number
  weight: number
  issues: string[]
  suggestions: string[]
}>()

const scoreClass = computed(() => {
  if (props.score >= 80) return 'high'
  if (props.score >= 60) return 'medium'
  return 'low'
})
</script>

<style scoped>
.dimension-card {
  padding: 20px;
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
}

.dim-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 12px;
}

.dim-name {
  font-weight: 700;
  font-size: 14.5px;
  color: var(--nm-text-primary);
}

.dim-score-box {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.score-val {
  font-size: 24px;
  font-weight: 800;
  line-height: 1;
}

.score-val.high { color: var(--nm-success); }
.score-val.medium { color: var(--nm-warning); }
.score-val.low { color: var(--nm-danger); }

.score-max {
  font-size: 12px;
  color: var(--nm-text-light);
}

/* 拟物凹槽进度条 */
.nm-progress-track {
  height: 8px;
  background: var(--nm-bg);
  border-radius: var(--nm-radius-full);
  box-shadow: var(--nm-shadow-inset);
  overflow: hidden;
  margin-bottom: 10px;
}

.nm-progress-fill {
  height: 100%;
  border-radius: var(--nm-radius-full);
  transition: width 0.8s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.nm-progress-fill.high {
  background: var(--nm-success-gradient);
  box-shadow: 0 0 8px rgba(16, 185, 129, 0.5);
}

.nm-progress-fill.medium {
  background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%);
  box-shadow: 0 0 8px rgba(245, 158, 11, 0.5);
}

.nm-progress-fill.low {
  background: linear-gradient(135deg, #ef4444 0%, #f87171 100%);
  box-shadow: 0 0 8px rgba(239, 68, 68, 0.5);
}

.dim-weight-row {
  margin-bottom: 12px;
}

.weight-chip {
  font-size: 11px;
  color: var(--nm-text-light);
  background: rgba(255, 255, 255, 0.6);
  padding: 2px 7px;
  border-radius: 4px;
  box-shadow: inset 1px 1px 2px rgba(166, 180, 200, 0.25);
}

.feedback-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}

.feedback-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12px;
  line-height: 1.55;
  color: var(--nm-text-regular);
}

.item-icon {
  font-size: 14px;
  flex-shrink: 0;
  margin-top: 2px;
}

.issue-icon {
  color: var(--nm-danger);
}

.suggest-icon {
  color: var(--nm-success);
}

.item-text {
  flex: 1;
}
</style>
