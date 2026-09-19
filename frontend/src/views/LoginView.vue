<template>
  <div class="login-page">
    <!-- 背景光斑装饰 -->
    <div class="bg-orb orb-1" />
    <div class="bg-orb orb-2" />

    <div class="login-card">
      <div class="login-header">
        <div class="logo-box">
          <img :src="iconLogo" class="logo-icon-img" alt="MentorHub" />
        </div>
        <h1 class="system-title">MentorHub</h1>
        <p class="system-tagline">新一代多 Agent 协同 AI 教学辅导平台</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        class="login-form"
        @submit.prevent="handleLogin"
      >
        <el-form-item label="用户名" prop="username">
          <div class="nm-input-wrapper">
            <el-input
              v-model="form.username"
              placeholder="请输入用户名（如 student / teacher）"
              size="large"
              :prefix-icon="User"
            />
          </div>
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <div class="nm-input-wrapper">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              size="large"
              :prefix-icon="Lock"
              show-password
              @keyup.enter="handleLogin"
            />
          </div>
        </el-form-item>

        <button
          type="button"
          class="login-submit-btn"
          :class="{ 'is-loading': loading }"
          :disabled="loading"
          @click="handleLogin"
        >
          <span v-if="loading" class="btn-spinner" />
          <span v-else>登 录</span>
        </button>

        <!-- 快速测试提示 -->
        <div class="login-hints">
          <span class="hint-title"><el-icon class="hint-icon"><Opportunity /></el-icon> 快速测试账号：</span>
          <div class="hint-chips">
            <span class="chip" @click="fillAccount('student', '123456')">学员 student</span>
            <span class="chip" @click="fillAccount('teacher', '123456')">教师 teacher</span>
          </div>
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock, Opportunity } from '@element-plus/icons-vue'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import iconLogo from '@/assets/images/icon_logo.svg'

const router = useRouter()
const auth = useAuthStore()

const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

function fillAccount(u: string, p: string) {
  form.username = u
  form.password = p
}

async function handleLogin() {
  await formRef.value?.validate()
  loading.value = true
  try {
    const { data } = await authApi.login({
      username: form.username,
      password: form.password,
    })
    auth.login(data.access_token, {
      userId: data.user_id,
      role: data.role as 'student' | 'teacher' | 'admin',
      tenantId: '',
      username: form.username,
    })
    ElMessage.success('登录成功，欢迎回来！')
    router.push('/dashboard')
  } catch {
    ElMessage.error('用户名或密码错误')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--nm-bg);
  position: relative;
  overflow: hidden;
  padding: 20px;
  box-sizing: border-box;
}

/* 软弥散光晕 */
.bg-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.45;
  pointer-events: none;
}

.orb-1 {
  width: 450px;
  height: 450px;
  background: radial-gradient(circle, #93c5fd 0%, rgba(235, 240, 247, 0) 70%);
  top: -100px;
  right: -100px;
}

.orb-2 {
  width: 400px;
  height: 400px;
  background: radial-gradient(circle, #c4b5fd 0%, rgba(235, 240, 247, 0) 70%);
  bottom: -80px;
  left: -80px;
}

.login-card {
  width: 420px;
  max-width: 100%;
  background: var(--nm-bg);
  border-radius: var(--nm-radius-xl);
  box-shadow: 10px 10px 30px rgba(166, 180, 200, 0.65), -10px -10px 30px rgba(255, 255, 255, 1);
  border: 1px solid rgba(255, 255, 255, 0.9);
  padding: 40px 36px;
  box-sizing: border-box;
  position: relative;
  z-index: 1;
  animation: pop-in 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
}

.logo-box {
  width: 68px;
  height: 68px;
  border-radius: var(--nm-radius-lg);
  background: var(--nm-bg);
  box-shadow: 6px 6px 16px rgba(166, 180, 200, 0.5), -6px -6px 16px rgba(255, 255, 255, 0.95);
  border: var(--nm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
  animation: float-gentle 3.5s ease-in-out infinite;
}

.logo-icon-img {
  width: 44px;
  height: 44px;
  object-fit: contain;
}

.system-title {
  margin: 0 0 6px;
  font-size: 26px;
  font-weight: 800;
  background: linear-gradient(135deg, #1e293b 0%, #3b82f6 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: -0.5px;
}

.system-tagline {
  margin: 0;
  color: var(--nm-text-secondary);
  font-size: 13px;
}

.login-form {
  margin-top: 10px;
}

.login-form :deep(.el-form-item__label) {
  font-weight: 600;
  color: var(--nm-text-primary);
  margin-bottom: 6px;
}

.nm-input-wrapper {
  width: 100%;
}

.login-submit-btn {
  width: 100%;
  height: 46px;
  margin-top: 14px;
  background: var(--nm-primary-gradient);
  border: none;
  border-radius: var(--nm-radius-md);
  color: #ffffff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 6px 18px rgba(59, 130, 246, 0.4), 4px 4px 10px rgba(166, 180, 200, 0.3);
  transition: var(--nm-transition);
  display: flex;
  align-items: center;
  justify-content: center;
}

.login-submit-btn:hover:not(:disabled) {
  transform: translateY(-2px) scale(1.015);
  box-shadow: 0 8px 22px rgba(59, 130, 246, 0.5), 6px 6px 14px rgba(166, 180, 200, 0.4);
}

.login-submit-btn:active:not(:disabled) {
  transform: translateY(1px) scale(0.985);
  box-shadow: 0 2px 6px rgba(59, 130, 246, 0.3);
}

.login-submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.btn-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.login-hints {
  margin-top: 24px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.5);
  border-radius: var(--nm-radius-sm);
  box-shadow: inset 1px 1px 3px rgba(166, 180, 200, 0.25);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hint-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  color: var(--nm-text-secondary);
  font-weight: 500;
}

.hint-icon {
  color: #d97706;
  font-size: 13px;
}

.hint-chips {
  display: flex;
  gap: 8px;
}

.chip {
  font-size: 11px;
  color: var(--nm-primary);
  background: var(--nm-bg);
  padding: 3px 8px;
  border-radius: var(--nm-radius-full);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
  cursor: pointer;
  transition: var(--nm-transition);
  font-weight: 500;
}

.chip:hover {
  transform: translateY(-1px);
  color: var(--nm-primary-hover);
  box-shadow: var(--nm-shadow-hover);
}
</style>
