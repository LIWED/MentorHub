<template>
  <div class="setting-number">
    <div class="copy">
      <div class="label">{{ label }}</div>
      <div class="tip">{{ tip }}</div>
    </div>
    <el-input-number
      v-model="model"
      :min="min"
      :max="max"
      :step="step"
      controls-position="right"
      class="number-input"
    />
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  label: string
  tip: string
  min: number
  max: number
  step?: number
}>(), {
  step: 1,
})

const model = defineModel<number>({ required: true })
</script>

<style scoped>
.setting-number {
  min-height: 74px;
  padding: 13px 14px;
  border: var(--nm-border);
  border-radius: var(--nm-radius-md);
  background: rgba(255, 255, 255, 0.24);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.copy {
  min-width: 0;
}

.label {
  font-size: 13px;
  font-weight: 650;
  color: var(--nm-text-primary);
}

.tip {
  margin-top: 5px;
  color: var(--nm-text-light);
  font-size: 11px;
  line-height: 1.45;
}

.number-input {
  width: 112px;
  flex-shrink: 0;
}
</style>
