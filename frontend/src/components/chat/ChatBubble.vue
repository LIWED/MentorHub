<template>
  <div class="chat-bubble" :class="role">
    <div class="avatar-container">
      <div class="avatar-ring" :class="role">
        <img
          v-if="role === 'assistant'"
          :src="avatarAssistant"
          class="avatar-img assistant"
          alt="AI Tutor"
        />
        <img
          v-else
          :src="avatarStudent"
          class="avatar-img user"
          alt="Student"
        />
      </div>
    </div>
    <div class="bubble-body">
      <div class="bubble-content" :class="role">
        <div v-if="role === 'assistant'" class="assistant-badge">
          <span class="badge-dot" />
          <span class="badge-text">MentorHub AI</span>
        </div>
        <slot />
      </div>
      <div v-if="role === 'assistant' && sources?.length" class="sources-box">
        <el-collapse class="nm-sources-collapse">
          <el-collapse-item name="sources">
            <template #title>
              <div class="sources-title">
                <span>📚 参考来源（{{ sources.length }} 条）</span>
              </div>
            </template>
            <ul class="sources-list">
              <li v-for="(src, i) in sources" :key="i" class="source-item">
                <span class="source-idx">[{{ i + 1 }}]</span>
                <span class="source-text">{{ src }}</span>
              </li>
            </ul>
          </el-collapse-item>
        </el-collapse>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import avatarAssistant from '@/assets/images/avatar_assistant.svg'
import avatarStudent from '@/assets/images/avatar_student.svg'

defineProps<{
  role: 'user' | 'assistant'
  sources?: string[]
}>()
</script>

<style scoped>
.chat-bubble {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  animation: pop-in 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.chat-bubble.user {
  flex-direction: row-reverse;
}

.avatar-container {
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  padding-top: 2px;
}

.avatar-ring {
  width: 40px;
  height: 40px;
  border-radius: var(--nm-radius-full);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-sm);
  border: var(--nm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  transition: var(--nm-transition);
}

.avatar-ring.assistant {
  background: linear-gradient(135deg, #ffffff 0%, #e0f2fe 100%);
  border-color: #bae6fd;
}

.avatar-ring.user {
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border-color: #bfdbfe;
}

.avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.bubble-body {
  max-width: 78%;
  display: flex;
  flex-direction: column;
}

.bubble-content {
  padding: 12px 18px;
  border-radius: var(--nm-radius-lg);
  font-size: 14.5px;
  line-height: 1.65;
  word-break: break-word;
  position: relative;
  transition: var(--nm-transition);
}

/* 用户气泡：现代渐变 + 柔彩色阴影 */
.bubble-content.user {
  background: var(--nm-primary-gradient);
  color: #ffffff;
  box-shadow: 0 4px 14px rgba(59, 130, 246, 0.35), 3px 3px 8px rgba(166, 180, 200, 0.3);
  border-bottom-right-radius: 4px;
}

.bubble-content.user :deep(.md-content),
.bubble-content.user :deep(.md-content p),
.bubble-content.user :deep(.md-content span),
.bubble-content.user :deep(.md-content strong) {
  color: #ffffff !important;
}

/* AI 助手气泡：精致微拟物卡片，告别纯白单调 */
.bubble-content.assistant {
  background: linear-gradient(150deg, #ffffff 0%, #f8fafc 40%, #f1f5f9 100%);
  color: var(--nm-text-primary);
  box-shadow: 6px 6px 18px rgba(166, 180, 200, 0.3), -4px -4px 14px rgba(255, 255, 255, 0.95), inset 0 1px 1px rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(226, 232, 240, 0.85);
  border-top-color: #ffffff;
  border-left-color: #ffffff;
  border-bottom-left-radius: 4px;
  padding: 14px 20px;
}

.assistant-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 1px 8px;
  height: 20px;
  border-radius: var(--nm-radius-full);
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.15);
  color: var(--nm-primary);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.3px;
  margin-bottom: 8px;
  user-select: none;
}

.badge-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--nm-primary);
  box-shadow: 0 0 6px var(--nm-primary);
}

/* 来源折叠面板 */
.sources-box {
  margin-top: 8px;
}

.nm-sources-collapse {
  border: none !important;
  background: transparent !important;
}

.nm-sources-collapse :deep(.el-collapse-item__header) {
  background: var(--nm-bg) !important;
  border-radius: var(--nm-radius-sm);
  padding: 0 12px;
  height: 32px;
  font-size: 12px;
  color: var(--nm-text-secondary);
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 2px 2px 5px rgba(166, 180, 200, 0.25);
}

.nm-sources-collapse :deep(.el-collapse-item__wrap) {
  background: transparent !important;
  border: none !important;
}

.nm-sources-collapse :deep(.el-collapse-item__content) {
  padding: 8px 4px 0;
}

.sources-title {
  display: flex;
  align-items: center;
  font-size: 12px;
  font-weight: 500;
}

.sources-list {
  margin: 0;
  padding: 8px 12px;
  background: var(--nm-bg);
  border-radius: var(--nm-radius-sm);
  box-shadow: var(--nm-shadow-inset);
  list-style: none;
}

.source-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
  color: var(--nm-text-secondary);
  line-height: 1.5;
  margin-bottom: 4px;
}

.source-item:last-child {
  margin-bottom: 0;
}

.source-idx {
  font-weight: 600;
  color: var(--nm-primary);
  flex-shrink: 0;
}

.source-text {
  word-break: break-all;
}
</style>
