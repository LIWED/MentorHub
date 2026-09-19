<template>
  <el-container class="app-layout">
    <!-- 左侧导航栏 -->
    <el-aside
      :width="isCollapse ? '72px' : '230px'"
      class="sidebar-aside"
      :class="{ 'sidebar-aside--collapsed': isCollapse }"
    >
      <Sidebar :is-collapse="isCollapse" />
    </el-aside>

    <el-container direction="vertical" class="main-container">
      <!-- 顶部 Header -->
      <el-header class="app-header">
        <div class="header-left">
          <!-- 折叠/展开 切换按钮 -->
          <button
            class="nm-icon-btn collapse-toggle"
            :title="isCollapse ? '展开菜单' : '收起菜单'"
            @click="isCollapse = !isCollapse"
          >
            <el-icon><Fold v-if="!isCollapse" /><Expand v-else /></el-icon>
          </button>
          <div class="system-badge">
            <span class="system-title">MentorHub</span>
            <span class="system-sub">AI 教学空间</span>
          </div>
        </div>

        <div class="header-right">
          <!-- 用户个人信息胶囊 -->
          <el-dropdown @command="handleCommand" trigger="click">
            <div class="user-pill">
              <div class="user-avatar">
                <img :src="auth.isTeacher ? avatarTeacher : avatarStudent" class="user-avatar-img" />
              </div>
              <div class="user-info-text">
                <span class="username">{{ auth.user?.username ?? auth.user?.userId }}</span>
                <span class="role-badge" :class="auth.user?.role">
                  {{ roleLabel }}
                </span>
              </div>
              <el-icon class="dropdown-arrow"><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu class="nm-dropdown-menu">
                <div class="dropdown-user-header">
                  <div class="dropdown-username">{{ auth.user?.username ?? auth.user?.userId }}</div>
                  <div class="dropdown-role">权限：{{ roleLabel }}</div>
                </div>
                <el-dropdown-item command="logout" class="dropdown-logout-item">
                  <el-icon><SwitchButton /></el-icon>
                  <span>退出登录</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 路由懒加载进度条 -->
      <div class="nav-progress-bar" :class="{ active: navigating }">
        <div class="progress-glow" />
      </div>

      <!-- 内容区 -->
      <el-main class="app-main">
        <!-- keep-alive 仅保留 QAChatView 状态，导航离开时冻结而非销毁 -->
        <router-view v-slot="{ Component }" :key="routerViewKey">
          <transition name="page-fade" mode="out-in">
            <keep-alive :include="['QAChatView']">
              <component :is="Component" />
            </keep-alive>
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onErrorCaptured } from 'vue'
import { ArrowDown, Fold, Expand, SwitchButton } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import Sidebar from './Sidebar.vue'
import avatarStudent from '@/assets/images/avatar_student.svg'
import avatarTeacher from '@/assets/images/avatar_teacher.svg'

const auth = useAuthStore()
const router = useRouter()
const isCollapse = ref(false)

// 路由切换期间显示顶部发光进度条
const navigating = ref(false)
router.beforeEach(() => { navigating.value = true })
router.afterEach(() => { navigating.value = false })

// 错误边界：捕获 RouterView 崩溃并恢复
const routerViewKey = ref(0)
let lastRecoveryAt = 0
onErrorCaptured((_err, _instance, _info) => {
  const now = Date.now()
  if (now - lastRecoveryAt > 500) {
    lastRecoveryAt = now
    routerViewKey.value++
  }
  return false
})

const roleLabel = computed(() => {
  if (auth.user?.role === 'admin') return '管理员'
  if (auth.user?.role === 'teacher') return '教师'
  return '学员'
})

function handleCommand(cmd: string) {
  if (cmd === 'logout') {
    auth.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.app-layout {
  height: 100vh;
  background-color: var(--nm-bg);
  overflow: hidden;
}

.sidebar-aside {
  background-color: var(--nm-bg);
  border-right: 1px solid rgba(255, 255, 255, 0.9);
  box-shadow: 4px 0 16px rgba(166, 180, 200, 0.25);
  transition: width 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  overflow: hidden;
  z-index: 10;
}

.main-container {
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background-color: var(--nm-bg);
  border-bottom: 1px solid rgba(255, 255, 255, 0.8);
  box-shadow: 0 4px 12px rgba(166, 180, 200, 0.2);
  padding: 0 24px;
  height: 64px;
  z-index: 9;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.nm-icon-btn {
  width: 38px;
  height: 38px;
  border-radius: var(--nm-radius-sm);
  background: var(--nm-bg);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--nm-text-secondary);
  cursor: pointer;
  transition: var(--nm-transition);
}

.nm-icon-btn:hover {
  transform: translateY(-2px);
  box-shadow: var(--nm-shadow-hover);
  color: var(--nm-primary);
}

.nm-icon-btn:active {
  transform: translateY(1px);
  box-shadow: var(--nm-shadow-pressed);
}

.system-badge {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.system-title {
  font-size: 18px;
  font-weight: 700;
  background: linear-gradient(135deg, #1e293b 0%, #3b82f6 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: -0.5px;
}

.system-sub {
  font-size: 11px;
  color: var(--nm-text-light);
  font-weight: 500;
  padding: 1px 6px;
  background: rgba(255, 255, 255, 0.6);
  border-radius: 4px;
  box-shadow: inset 1px 1px 2px rgba(166, 180, 200, 0.3);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 用户药丸胶囊 */
.user-pill {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 12px 5px 6px;
  background: var(--nm-bg);
  border: var(--nm-border);
  border-radius: var(--nm-radius-full);
  box-shadow: var(--nm-shadow-sm);
  cursor: pointer;
  transition: var(--nm-transition);
  user-select: none;
}

.user-pill:hover {
  transform: translateY(-2px);
  box-shadow: var(--nm-shadow-hover);
}

.user-pill:active {
  transform: translateY(1px);
  box-shadow: var(--nm-shadow-pressed);
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: var(--nm-radius-full);
  background: linear-gradient(135deg, #ffffff 0%, #e2e8f0 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--nm-shadow-sm);
  overflow: hidden;
}

.user-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.user-info-text {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.username {
  font-size: 13px;
  font-weight: 600;
  color: var(--nm-text-primary);
}

.role-badge {
  font-size: 10px;
  color: var(--nm-text-light);
}

.role-badge.teacher, .role-badge.admin {
  color: var(--nm-primary);
  font-weight: 600;
}

.dropdown-arrow {
  font-size: 12px;
  color: var(--nm-text-light);
  margin-left: 2px;
}

.dropdown-user-header {
  padding: 10px 16px;
  border-bottom: 1px solid rgba(203, 213, 225, 0.4);
}

.dropdown-username {
  font-size: 13px;
  font-weight: 600;
  color: var(--nm-text-primary);
}

.dropdown-role {
  font-size: 11px;
  color: var(--nm-text-light);
  margin-top: 2px;
}

.dropdown-logout-item {
  color: var(--nm-danger) !important;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 顶部进度条 */
.nav-progress-bar {
  height: 3px;
  background: transparent;
  overflow: hidden;
  position: relative;
  flex-shrink: 0;
}

.nav-progress-bar.active {
  background: rgba(59, 130, 246, 0.15);
}

.nav-progress-bar.active .progress-glow {
  height: 100%;
  width: 45%;
  background: var(--nm-primary-gradient);
  box-shadow: 0 0 10px rgba(59, 130, 246, 0.8);
  animation: nav-scan 0.85s ease-in-out infinite;
}

@keyframes nav-scan {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(300%); }
}

.app-main {
  background: var(--nm-bg);
  overflow-y: auto;
  padding: 24px;
}

/* 页面切换动画 */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
