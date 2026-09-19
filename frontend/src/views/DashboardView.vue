<template>
  <div class="dashboard">
    <!-- 顶部欢迎横幅 -->
    <div class="welcome-banner">
      <div class="welcome-left">
        <div class="avatar-ring">
          <img
            :src="auth.isTeacher ? avatarTeacher : avatarStudent"
            class="user-avatar-img"
            :alt="auth.user?.username"
          />
        </div>
        <div class="welcome-text">
          <h2 class="welcome-greeting">
            {{ greetingText }}，{{ auth.user?.username ?? auth.user?.userId }}
          </h2>
          <p class="welcome-sub">
            今天想探索什么新知识？选择以下 AI 智能 Agent 开始学习旅程。
          </p>
        </div>
      </div>
      <div class="welcome-right">
        <div class="status-chip">
          <span class="pulse-dot" />
          <span>AI 协同中心在线</span>
        </div>
      </div>
    </div>

    <!-- AI 助手入口（Hero 卡片，突出展示） -->
    <div class="ai-hero-card" @click="router.push('/chat')">
      <div class="ai-hero-shine" />
      <div class="ai-card-content">
        <div class="ai-card-left">
          <div class="ai-sparkle-box">
            <img :src="iconAiHero" class="ai-hero-icon-img" alt="AI Core" />
          </div>
          <div class="ai-text-box">
            <div class="ai-title-row">
              <span class="ai-title">统一 AI 助手</span>
              <span class="ai-badge">多 Agent 协同</span>
            </div>
            <div class="ai-desc">
              直接自然语言描述您的学习或备考需求，系统将自动识别意图并路由至对应 Agent，甚至串联多 Agent 协同服务！
            </div>
            <div class="agent-pills">
              <span class="agent-pill">
                <img :src="iconQa" class="pill-thumb" /> KnowFlow QA
              </span>
              <span class="agent-pill">
                <img :src="iconExam" class="pill-thumb" /> 试卷智能批改
              </span>
              <span class="agent-pill">
                <img :src="iconResume" class="pill-thumb" /> 简历诊断
              </span>
              <span class="agent-pill">
                <img :src="iconInterview" class="pill-thumb" /> 模拟面试
              </span>
            </div>
          </div>
        </div>
        <div class="ai-card-right">
          <button class="hero-cta-btn">
            <span>立即对话</span>
            <el-icon class="arrow-icon"><ArrowRight /></el-icon>
          </button>
        </div>
      </div>
    </div>

    <!-- 四个独立功能入口 -->
    <div class="section-title-row">
      <span class="section-title">核心功能 Agent</span>
      <span class="section-sub">针对特定教学与求职场景的专业能力</span>
    </div>

    <el-row :gutter="20" class="feature-cards">
      <el-col
        v-for="card in featureCards"
        :key="card.route"
        :xs="24"
        :sm="12"
        :md="6"
        style="margin-bottom: 20px"
      >
        <div class="feature-card" @click="router.push(card.route)">
          <div class="card-icon-well">
            <img :src="card.iconImg" class="feature-icon-img" :alt="card.title" />
          </div>
          <div class="card-title">{{ card.title }}</div>
          <div class="card-desc">{{ card.desc }}</div>
          <div class="card-footer">
            <button class="card-action-btn">
              <span>{{ card.action }}</span>
              <el-icon><ArrowRight /></el-icon>
            </button>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

import iconQa from '@/assets/images/icon_qa.jpg'
import iconExam from '@/assets/images/icon_exam.jpg'
import iconResume from '@/assets/images/icon_resume.jpg'
import iconInterview from '@/assets/images/icon_interview.svg'
import iconAiHero from '@/assets/images/icon_ai_hero.svg'
import avatarStudent from '@/assets/images/avatar_student.svg'
import avatarTeacher from '@/assets/images/avatar_teacher.svg'

const router = useRouter()
const auth = useAuthStore()

const greetingText = computed(() => {
  const hour = new Date().getHours()
  if (hour < 6) return '夜深了'
  if (hour < 12) return '早上好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
})

const featureCards = [
  {
    iconImg: iconQa,
    title: '智能问答',
    desc: '7×24小时即时响应，多轮追问，RAG 知识库深度检索与 Web 联网增强',
    action: '开始问答',
    route: '/qa',
  },
  {
    iconImg: iconExam,
    title: '试卷批改',
    desc: 'AI 预批改 + 知识薄弱点定位，自动评分与人工教师确认双轨保障',
    action: '提交试卷',
    route: '/exam',
  },
  {
    iconImg: iconResume,
    title: '简历审查',
    desc: '六维度写作质量深度评审，精准原文定位与可落地的定制化修改建议',
    action: '上传简历',
    route: '/resume',
  },
  {
    iconImg: iconInterview,
    title: '模拟面试',
    desc: '技术原理 + 项目深挖双轨考察，多阶段自适应问答并生成全方位诊断报告',
    action: '开始面试',
    route: '/interview',
  },
]
</script>

<style scoped>
.dashboard {
  max-width: 1200px;
  margin: 0 auto;
  animation: pop-in 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* 欢迎横幅 */
.welcome-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 16px;
}

.welcome-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.avatar-ring {
  width: 54px;
  height: 54px;
  border-radius: var(--nm-radius-lg);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-sm);
  border: var(--nm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.user-emoji {
  font-size: 28px;
}

.welcome-greeting {
  margin: 0 0 4px;
  font-size: 22px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

.welcome-sub {
  margin: 0;
  font-size: 13.5px;
  color: var(--nm-text-secondary);
}

.status-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: var(--nm-bg);
  border: var(--nm-border);
  border-radius: var(--nm-radius-full);
  box-shadow: var(--nm-shadow-sm);
  font-size: 12px;
  color: var(--nm-text-regular);
  font-weight: 500;
}

.pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--nm-success);
  box-shadow: 0 0 8px var(--nm-success);
  animation: pulse-glow 2s infinite;
}

/* AI 助手 Hero 卡片 */
.ai-hero-card {
  position: relative;
  background: linear-gradient(135deg, #e0f2fe 0%, #eef2f7 50%, #f3e8ff 100%);
  border-radius: var(--nm-radius-xl);
  border: 1px solid rgba(255, 255, 255, 0.9);
  box-shadow: 8px 8px 24px rgba(166, 180, 200, 0.6), -8px -8px 24px rgba(255, 255, 255, 0.95);
  padding: 24px 28px;
  cursor: pointer;
  overflow: hidden;
  margin-bottom: 32px;
  transition: var(--nm-transition);
}

.ai-hero-card:hover {
  transform: translateY(-4px) scale(1.008);
  box-shadow: 12px 12px 30px rgba(166, 180, 200, 0.7), -12px -12px 30px rgba(255, 255, 255, 1);
}

.ai-hero-card:hover .ai-sparkle-box {
  transform: scale(1.12) rotate(10deg);
}

.ai-hero-card:hover .hero-cta-btn {
  transform: scale(1.05);
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.5);
}

.ai-card-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
}

.ai-card-left {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  flex: 1;
  min-width: 280px;
}

.ai-sparkle-box {
  width: 58px;
  height: 58px;
  border-radius: var(--nm-radius-lg);
  background: #ffffff;
  box-shadow: 4px 4px 12px rgba(166, 180, 200, 0.4), -4px -4px 12px rgba(255, 255, 255, 1);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: var(--nm-transition);
}

.ai-sparkle-emoji {
  font-size: 32px;
  animation: float-gentle 3s ease-in-out infinite;
}

.ai-text-box {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ai-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ai-title {
  font-size: 19px;
  font-weight: 700;
  color: var(--nm-text-primary);
  letter-spacing: -0.3px;
}

.ai-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--nm-radius-full);
  background: var(--nm-primary-gradient);
  color: #ffffff;
  font-weight: 600;
  box-shadow: 0 2px 6px rgba(59, 130, 246, 0.4);
}

.ai-desc {
  font-size: 13.5px;
  color: var(--nm-text-regular);
  line-height: 1.5;
  max-width: 650px;
}

.agent-pills {
  display: flex;
  gap: 8px;
  margin-top: 6px;
  flex-wrap: wrap;
}

.agent-pill {
  font-size: 11px;
  padding: 3px 9px;
  border-radius: var(--nm-radius-full);
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.9);
  color: var(--nm-text-secondary);
  box-shadow: 2px 2px 5px rgba(166, 180, 200, 0.25);
  font-weight: 500;
}

.hero-cta-btn {
  padding: 10px 22px;
  border-radius: var(--nm-radius-full);
  background: var(--nm-primary-gradient);
  border: none;
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(59, 130, 246, 0.4);
  transition: var(--nm-transition);
}

.arrow-icon {
  font-size: 14px;
  transition: transform 0.2s ease;
}

.hero-cta-btn:hover .arrow-icon {
  transform: translateX(3px);
}

/* 区域标题 */
.section-title-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 18px;
}

.section-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

.section-sub {
  font-size: 12.5px;
  color: var(--nm-text-light);
}

/* 独立功能卡片 */
.feature-card {
  height: 100%;
  background: var(--nm-bg);
  border-radius: var(--nm-radius-xl);
  box-shadow: var(--nm-shadow-flat);
  border: var(--nm-border);
  padding: 24px 20px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  cursor: pointer;
  transition: var(--nm-transition);
  position: relative;
}

.feature-card:hover {
  transform: translateY(-5px) scale(1.015);
  box-shadow: var(--nm-shadow-hover);
}

.feature-card:hover .card-icon-well {
  transform: scale(1.1) rotate(6deg);
}

.feature-card:hover .card-action-btn {
  background: var(--nm-primary);
  color: #ffffff;
  box-shadow: 0 4px 10px rgba(59, 130, 246, 0.35);
}

.user-avatar-img {
  width: 100%;
  height: 100%;
  border-radius: var(--nm-radius-lg);
  object-fit: cover;
}

.ai-hero-icon-img {
  width: 44px;
  height: 44px;
  object-fit: contain;
  animation: float-gentle 3s ease-in-out infinite;
}

.pill-thumb {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  object-fit: cover;
  vertical-align: -2px;
  margin-right: 2px;
}

.card-icon-well {
  width: 72px;
  height: 72px;
  border-radius: var(--nm-radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
  box-shadow: 4px 4px 12px rgba(166, 180, 200, 0.4), -4px -4px 12px rgba(255, 255, 255, 0.9);
  transition: var(--nm-transition);
  overflow: hidden;
  background: var(--nm-bg);
}

.feature-icon-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: var(--nm-radius-lg);
}

.card-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--nm-text-primary);
  margin-bottom: 8px;
}

.card-desc {
  font-size: 12.5px;
  color: var(--nm-text-secondary);
  line-height: 1.55;
  margin-bottom: 18px;
  flex: 1;
}

.card-footer {
  width: 100%;
}

.card-action-btn {
  width: 100%;
  padding: 8px 14px;
  border-radius: var(--nm-radius-md);
  background: var(--nm-bg);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
  color: var(--nm-text-regular);
  font-size: 12.5px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  transition: var(--nm-transition);
}

.card-action-btn:active {
  transform: translateY(1px);
  box-shadow: var(--nm-shadow-pressed);
}
</style>
