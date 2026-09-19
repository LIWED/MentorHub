<template>
  <div class="stage-bar-container">
    <div class="stage-bar">
      <div
        v-for="(stage, i) in stages"
        :key="stage.key"
        class="stage-item"
        :class="{
          done: stageOrder.indexOf(stage.key) < currentIndex,
          active: stage.key === current,
          pending: stageOrder.indexOf(stage.key) > currentIndex,
        }"
      >
        <div class="stage-dot-wrapper">
          <div class="stage-dot">
            <el-icon v-if="stageOrder.indexOf(stage.key) < currentIndex"><Check /></el-icon>
            <span v-else>{{ i + 1 }}</span>
          </div>
          <div v-if="stage.key === current" class="active-pulse-ring" />
        </div>
        <div class="stage-label">{{ stage.label }}</div>
        <div v-if="i < stages.length - 1" class="stage-track" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Check } from '@element-plus/icons-vue'

const stages = [
  { key: 'warmup', label: '热身介绍' },
  { key: 'tech_base', label: '基础考核' },
  { key: 'project', label: '项目深挖' },
  { key: 'closing', label: '反问总结' },
  { key: 'finished', label: '面试完成' },
]

const stageOrder = stages.map(s => s.key)
const props = defineProps<{ current: string }>()
const currentIndex = computed(() => stageOrder.indexOf(props.current))
</script>

<style scoped>
.stage-bar-container {
  padding: 14px 20px;
  background: var(--nm-bg);
  border-radius: var(--nm-radius-lg);
  box-shadow: var(--nm-shadow-flat);
  border: var(--nm-border);
}

.stage-bar {
  display: flex;
  align-items: center;
  position: relative;
}

.stage-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
  flex: 1;
}

.stage-dot-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2;
}

.stage-dot {
  width: 32px;
  height: 32px;
  border-radius: var(--nm-radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-sm);
  border: var(--nm-border);
  color: var(--nm-text-light);
  transition: var(--nm-transition);
}

.stage-item.done .stage-dot {
  background: var(--nm-success-gradient);
  color: #ffffff;
  border: none;
  box-shadow: 0 4px 10px rgba(16, 185, 129, 0.4);
}

.stage-item.active .stage-dot {
  background: var(--nm-primary-gradient);
  color: #ffffff;
  border: none;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.5);
}

.active-pulse-ring {
  position: absolute;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  border: 2px solid var(--nm-primary);
  opacity: 0.6;
  animation: pulse-glow 2s infinite;
  pointer-events: none;
}

.stage-label {
  font-size: 12px;
  margin-top: 6px;
  color: var(--nm-text-light);
  font-weight: 500;
  transition: var(--nm-transition);
}

.stage-item.active .stage-label {
  color: var(--nm-primary);
  font-weight: 700;
}

.stage-item.done .stage-label {
  color: var(--nm-success);
}

/* 进度连接槽 */
.stage-track {
  position: absolute;
  top: 16px;
  left: 50%;
  width: 100%;
  height: 4px;
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-inset);
  z-index: 1;
  border-radius: var(--nm-radius-full);
}

.stage-item.done .stage-track {
  background: var(--nm-success);
  box-shadow: 0 0 6px rgba(16, 185, 129, 0.5);
}
</style>
