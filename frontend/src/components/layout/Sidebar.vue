<template>
  <div class="sidebar" :class="{ 'sidebar--collapsed': isCollapse }">
    <!-- 顶部 Logo 区域 -->
    <div class="logo">
      <div class="logo-icon-wrapper">
        <img :src="iconLogo" class="logo-icon-img" alt="MentorHub" />
      </div>
      <div v-show="!isCollapse" class="logo-text-wrapper">
        <span class="logo-title">MentorHub</span>
        <span class="logo-tag">EDU AI</span>
      </div>
    </div>

    <!-- 导航菜单列表 -->
    <nav class="nav-list">
      <el-tooltip
        v-for="item in studentNavItems"
        :key="item.path"
        :content="item.title"
        placement="right"
        :disabled="!isCollapse"
      >
        <RouterLink
          :to="item.path"
          class="nav-item"
          :class="{ 'nav-item--active': isActive(item.path) }"
        >
          <div class="nav-icon-box">
            <component :is="item.icon" />
          </div>
          <span v-show="!isCollapse" class="nav-label">{{ item.title }}</span>
          <div v-if="isActive(item.path)" class="active-indicator" />
        </RouterLink>
      </el-tooltip>

      <!-- 教师端菜单（仅 teacher/admin 可见） -->
      <template v-if="auth.isTeacher">
        <div class="nav-divider">
          <span v-show="!isCollapse" class="divider-label">教师管理</span>
        </div>

        <el-tooltip
          v-for="item in teacherNavItems"
          :key="item.path"
          :content="item.title"
          placement="right"
          :disabled="!isCollapse"
        >
          <RouterLink
            :to="item.path"
            class="nav-item"
            :class="{ 'nav-item--active': isActive(item.path) }"
          >
            <div class="nav-icon-box">
              <component :is="item.icon" />
            </div>
            <span v-show="!isCollapse" class="nav-label">{{ item.title }}</span>
            <div v-if="isActive(item.path)" class="active-indicator" />
          </RouterLink>
        </el-tooltip>
      </template>

      <template v-if="auth.isAdmin">
        <div class="nav-divider">
          <span v-show="!isCollapse" class="divider-label">系统</span>
        </div>

        <el-tooltip
          v-for="item in adminNavItems"
          :key="item.path"
          :content="item.title"
          placement="right"
          :disabled="!isCollapse"
        >
          <RouterLink
            :to="item.path"
            class="nav-item"
            :class="{ 'nav-item--active': isActive(item.path) }"
          >
            <div class="nav-icon-box">
              <component :is="item.icon" />
            </div>
            <span v-show="!isCollapse" class="nav-label">{{ item.title }}</span>
            <div v-if="isActive(item.path)" class="active-indicator" />
          </RouterLink>
        </el-tooltip>
      </template>
    </nav>
  </div>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import {
  House, ChatDotRound, Document, Postcard,
  Microphone, EditPen, Collection, Setting,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import iconLogo from '@/assets/images/icon_logo.svg'

defineProps<{
  isCollapse?: boolean
}>()

const auth = useAuthStore()
const route = useRoute()

const studentNavItems = [
  { path: '/dashboard', title: '首页概览', icon: House },
  { path: '/qa', title: '智能问答', icon: ChatDotRound },
  { path: '/exam', title: '试卷批改', icon: Document },
  { path: '/resume', title: '简历审查', icon: Postcard },
  { path: '/interview', title: '模拟面试', icon: Microphone },
]

const teacherNavItems = [
  { path: '/teacher/exam-review', title: '批改确认', icon: EditPen },
  { path: '/teacher/knowledge-pending', title: '知识库补充', icon: Collection },
]

const adminNavItems = [
  { path: '/settings', title: '系统设置', icon: Setting },
]

function isActive(prefix: string) {
  return route.path === prefix || route.path.startsWith(prefix + '/')
}
</script>

<style scoped>
.sidebar {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--nm-bg);
  padding: 12px 10px;
  box-sizing: border-box;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 10px;
  margin-bottom: 12px;
  user-select: none;
}

.logo-icon-wrapper {
  width: 42px;
  height: 42px;
  border-radius: var(--nm-radius-md);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-sm);
  border: var(--nm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: var(--nm-transition);
}

.logo-icon-wrapper:hover {
  transform: rotate(-8deg) scale(1.08);
  box-shadow: var(--nm-shadow-hover);
}

.logo-icon-img {
  width: 28px;
  height: 28px;
  object-fit: contain;
}

.logo-text-wrapper {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  white-space: nowrap;
}

.logo-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--nm-text-primary);
  letter-spacing: -0.3px;
}

.logo-tag {
  font-size: 10px;
  font-weight: 600;
  color: var(--nm-primary);
  letter-spacing: 0.5px;
}

.nav-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  color: var(--nm-text-regular);
  text-decoration: none;
  font-size: 13.5px;
  font-weight: 500;
  border-radius: var(--nm-radius-md);
  background: var(--nm-bg);
  border: 1px solid transparent;
  box-shadow: none;
  cursor: pointer;
  transition: var(--nm-transition);
  position: relative;
  user-select: none;
  white-space: nowrap;
}

.nav-item:hover {
  color: var(--nm-primary);
  transform: translateX(3px);
  box-shadow: var(--nm-shadow-sm);
  border: var(--nm-border);
}

.nav-item:hover .nav-icon-box {
  transform: scale(1.15) rotate(4deg);
  color: var(--nm-primary);
}

/* 激活态：拟物凹陷槽质感 */
.nav-item--active {
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-inset) !important;
  color: var(--nm-primary) !important;
  font-weight: 600;
  border: 1px solid rgba(255, 255, 255, 0.4) !important;
  transform: none !important;
}

.nav-icon-box {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
  transition: var(--nm-transition);
}

.nav-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.active-indicator {
  width: 5px;
  height: 18px;
  border-radius: var(--nm-radius-full);
  background: var(--nm-primary);
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.7);
  position: absolute;
  right: 8px;
}

.nav-divider {
  padding: 14px 10px 6px;
}

.divider-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--nm-text-light);
  letter-spacing: 0.5px;
  text-transform: uppercase;
}

/* 折叠状态 */
.sidebar--collapsed .nav-item {
  padding: 10px 0;
  justify-content: center;
}

.sidebar--collapsed .logo {
  padding: 0;
  justify-content: center;
}
</style>
