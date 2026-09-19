<template>
  <div class="exam-review-page">
    <div class="nm-card review-list-card">
      <div class="card-header">
        <div class="header-icon-box">
          <span class="header-icon">✍️</span>
        </div>
        <div style="flex: 1">
          <h3 class="card-title">待确认批改试卷列表</h3>
          <p class="card-subtitle">AI 预批改后标记需教师复核确认的试卷档案</p>
        </div>
        <button class="nm-icon-refresh-btn" title="刷新列表" @click="fetchList">
          <el-icon><Refresh /></el-icon>
        </button>
      </div>

      <div v-if="!list.length && !loading" class="empty-list">
        <el-empty description="当前暂无待确认的批改试卷" />
      </div>

      <el-table v-else :data="list" v-loading="loading" size="default" class="review-table">
        <el-table-column prop="student_name" label="学员姓名" width="130">
          <template #default="{ row }">
            <span class="student-name-text">👤 {{ row.student_name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="exam_title" label="试卷名称" min-width="180">
          <template #default="{ row }">
            <span class="exam-title-text">{{ row.exam_title }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="submitted_at" label="提交时间" width="180">
          <template #default="{ row }">
            <span class="time-text">{{ row.submitted_at }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AI 预评分" width="130">
          <template #default="{ row }">
            <span class="score-pill">
              {{ row.pre_review?.total_score }} / {{ row.pre_review?.full_score }} 分
            </span>
          </template>
        </el-table-column>
        <el-table-column label="待确认题数" width="120" align="center">
          <template #default="{ row }">
            <span class="needs-review-chip">
              {{ row.pre_review?.needs_review_count }} 题待审
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110" align="center">
          <template #default="{ row }">
            <button
              class="table-review-btn"
              type="button"
              @click="openReview(row.submission_id)"
            >
              审阅批改
            </button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 审阅抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      title="教师批改复核与确认"
      size="65%"
      direction="rtl"
      destroy-on-close
      class="nm-drawer"
    >
      <div v-if="currentReview" class="review-drawer-content">
        <!-- 汇总信息卡片 -->
        <div class="nm-card drawer-summary-card">
          <div class="summary-grid">
            <div class="summary-item">
              <span class="sum-label">AI 预评分</span>
              <div class="sum-val">
                <b>{{ currentReview.pre_review_summary?.total_score }}</b>
                <span class="sum-max">/ {{ currentReview.pre_review_summary?.full_score }} 分</span>
              </div>
            </div>

            <div class="summary-item">
              <span class="sum-label">待确认题目</span>
              <div class="sum-val">
                <span class="needs-count-tag">
                  {{ currentReview.pre_review_summary?.by_question?.filter(q => q.needs_review).length }} 题需确认
                </span>
              </div>
            </div>

            <div class="summary-item">
              <span class="sum-label">薄弱知识点</span>
              <div class="sum-val">
                <span v-if="!currentReview.weak_points?.length" style="color: #94a3b8">暂无</span>
                <span
                  v-for="wp in currentReview.weak_points?.slice(0, 3)"
                  :key="wp.tag"
                  class="drawer-weak-chip"
                >
                  {{ wp.tag }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- 逐题列表 -->
        <el-collapse v-model="expandedKeys" class="nm-collapse">
          <el-collapse-item
            v-for="q in currentReview.pre_review_summary?.by_question"
            :key="q.question_id"
            :name="q.question_id"
          >
            <template #title>
              <div class="q-title-row">
                <span class="q-no">第 {{ q.question_no }} 题</span>
                <span class="type-tag" :class="q.question_type">
                  {{ typeLabel(q.question_type) }}
                </span>
                <span
                  class="score-tag"
                  :class="{
                    'changed': scoreChanged(q),
                    'needs-review': q.needs_review && !scoreChanged(q),
                    'normal': !q.needs_review && !scoreChanged(q)
                  }"
                >
                  {{ scoreChanged(q) ? '已改分 ' + modifications[q.question_id]?.new_score : q.score }}
                  / {{ q.full_score }} 分
                  <span v-if="q.needs_review && !scoreChanged(q)">· 需核准</span>
                </span>
              </div>
            </template>

            <div class="q-detail">
              <!-- 题目内容 -->
              <div v-if="q.content" class="q-section">
                <div class="q-label">题目描述</div>
                <div class="q-content">{{ q.content }}</div>
              </div>

              <!-- 学员答案 & 参考答案 -->
              <div class="q-row">
                <div class="q-col">
                  <div class="q-label">学员作答</div>
                  <div class="q-answer student">{{ q.student_answer || '（未作答）' }}</div>
                </div>
                <div v-if="q.correct_answer" class="q-col">
                  <div class="q-label">参考答案</div>
                  <div class="q-answer correct">{{ q.correct_answer }}</div>
                </div>
              </div>

              <!-- AI 反馈 -->
              <div class="q-section">
                <div class="q-label">AI 批改结论</div>
                <div class="q-feedback">{{ q.ai_feedback }}</div>
              </div>

              <!-- 得分点（简答题） -->
              <div v-if="q.point_results?.length" class="q-section">
                <div class="q-label">得分点核算明细</div>
                <div v-for="(pt, i) in q.point_results" :key="i" class="point-row">
                  <el-icon :color="pt.earned ? '#10b981' : '#ef4444'">
                    <component :is="pt.earned ? 'CircleCheck' : 'CircleClose'" />
                  </el-icon>
                  <span style="margin-left: 6px; font-weight: 500">{{ pt.point_desc }}（{{ pt.point_score }}分）</span>
                  <span v-if="!pt.earned && pt.missing" style="color:#ef4444; margin-left: 6px">
                    — {{ pt.missing }}
                  </span>
                </div>
              </div>

              <!-- 代码题：测试用例 -->
              <div v-if="q.question_type === 'code'" class="q-section">
                <div class="q-label">代码测试用例</div>
                <span v-if="q.sandbox_skipped" style="color:#94a3b8; font-size: 13px">Judge0 沙箱跳过</span>
                <span v-else class="test-pass-text">通过 {{ q.test_cases_passed }} / {{ q.test_cases_total }} 测试用例</span>
              </div>

              <!-- 教师改分区 -->
              <div class="q-modify-row">
                <span class="modify-label">教师复核改分：</span>
                <el-input-number
                  v-model="modifications[q.question_id].new_score"
                  :min="0"
                  :max="q.full_score"
                  size="default"
                  style="width: 120px"
                  @change="onScoreChange(q)"
                />
                <span class="max-score-hint">/ {{ q.full_score }} 分</span>
                <el-input
                  v-model="modifications[q.question_id].comment"
                  placeholder="填写教师批注意见（可选）"
                  size="default"
                  style="flex: 1; min-width: 200px"
                />
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>

        <!-- 底部确认发布操作栏 -->
        <div class="action-bar">
          <div class="action-hint">
            <span v-if="changedCount === 0">AI 批改结论未作变更，确认后将按原预评分发布给学员。</span>
            <span v-else>已调整 <b>{{ changedCount }}</b> 题分数，确认后将以教师调整分数为准正式发布。</span>
          </div>
          <div class="action-btns">
            <button class="nm-button cancel-btn" @click="drawerVisible = false" :disabled="confirming">
              取消
            </button>
            <button class="nm-button-primary confirm-publish-btn" :disabled="confirming" @click="confirmReview">
              <span v-if="confirming" class="btn-spinner" />
              <span v-else>{{ changedCount > 0 ? '修改后确认发布' : '直接确认发布' }}</span>
            </button>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { examApi, type PendingReviewItem, type ReviewDetail } from '@/api/exam'

const loading = ref(false)
const list = ref<PendingReviewItem[]>([])
const drawerVisible = ref(false)
const currentReview = ref<ReviewDetail | null>(null)
const confirming = ref(false)
const expandedKeys = ref<string[]>([])

// 每题：{ new_score, comment }
const modifications = reactive<Record<string, { new_score: number; comment: string }>>({})

const changedCount = computed(() => {
  if (!currentReview.value) return 0
  return currentReview.value.pre_review_summary.by_question.filter(q => scoreChanged(q)).length
})

function scoreChanged(q: { question_id: string; score: number }) {
  const mod = modifications[q.question_id]
  return mod !== undefined && mod.new_score !== q.score
}

function onScoreChange(_q: { question_id: string; score: number }) {
  // reactive handles updates
}

function typeLabel(type: string) {
  const map: Record<string, string> = {
    single_choice: '单选',
    multi_choice:  '多选',
    judge:         '判断',
    short_answer:  '简答',
    code:          '代码',
  }
  return map[type] ?? type
}

async function fetchList() {
  loading.value = true
  try {
    const { data } = await examApi.getPendingReviews()
    list.value = data.items
  } finally {
    loading.value = false
  }
}

async function openReview(submissionId: string) {
  const { data } = await examApi.getSubmissionReviewTeacher(submissionId)
  currentReview.value = data

  for (const q of data.pre_review_summary?.by_question ?? []) {
    modifications[q.question_id] = { new_score: q.score, comment: '' }
  }

  expandedKeys.value = (data.pre_review_summary?.by_question ?? [])
    .filter(q => q.needs_review)
    .map(q => q.question_id)

  drawerVisible.value = true
}

async function confirmReview() {
  if (!currentReview.value) return
  confirming.value = true
  try {
    const questions = currentReview.value.pre_review_summary.by_question ?? []

    const changedMods = questions
      .filter(q => scoreChanged(q))
      .map(q => ({
        question_id: q.question_id,
        new_score:   modifications[q.question_id].new_score,
        comment:     modifications[q.question_id].comment || undefined,
      }))

    const action = changedMods.length > 0 ? 'modify' : 'approve'

    await examApi.confirmReview(currentReview.value.submission_id, {
      action,
      modifications: changedMods,
    })

    ElMessage.success('批改结果已成功发布给学员')
    drawerVisible.value = false
    fetchList()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail ?? '发布失败，请重试')
  } finally {
    confirming.value = false
  }
}

onMounted(fetchList)
</script>

<style scoped>
.exam-review-page {
  max-width: 1100px;
  margin: 0 auto;
  animation: pop-in 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.review-list-card {
  padding: 24px 28px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 22px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(203, 213, 225, 0.4);
}

.header-icon-box {
  width: 44px;
  height: 44px;
  border-radius: var(--nm-radius-md);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-sm);
  border: var(--nm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.header-icon {
  font-size: 22px;
}

.card-title {
  margin: 0 0 4px;
  font-size: 17px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

.card-subtitle {
  margin: 0;
  font-size: 12.5px;
  color: var(--nm-text-secondary);
}

.nm-icon-refresh-btn {
  width: 34px;
  height: 34px;
  border-radius: var(--nm-radius-sm);
  background: var(--nm-bg);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
  color: var(--nm-text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: var(--nm-transition);
}

.nm-icon-refresh-btn:hover {
  transform: rotate(180deg);
  color: var(--nm-primary);
  box-shadow: var(--nm-shadow-hover);
}

.student-name-text {
  font-weight: 600;
  color: var(--nm-text-primary);
}

.exam-title-text {
  font-weight: 500;
  color: var(--nm-text-primary);
}

.time-text {
  font-size: 12.5px;
  color: var(--nm-text-secondary);
}

.score-pill {
  font-size: 12px;
  font-weight: 700;
  color: var(--nm-primary);
  background: #eff6ff;
  padding: 2px 8px;
  border-radius: var(--nm-radius-full);
}

.needs-review-chip {
  font-size: 11px;
  color: #d97706;
  background: #fef3c7;
  padding: 2px 8px;
  border-radius: var(--nm-radius-full);
  font-weight: 600;
}

.table-review-btn {
  padding: 4px 14px;
  border-radius: var(--nm-radius-full);
  background: var(--nm-bg);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
  color: var(--nm-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: var(--nm-transition);
}

.table-review-btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--nm-shadow-hover);
}

/* 审阅抽屉内容 */
.review-drawer-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 8px 4px;
}

.drawer-summary-card {
  padding: 16px 20px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sum-label {
  font-size: 11.5px;
  color: var(--nm-text-light);
  font-weight: 600;
}

.sum-val {
  font-size: 14px;
  color: var(--nm-text-primary);
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.sum-max {
  font-size: 12px;
  color: var(--nm-text-light);
}

.needs-count-tag {
  font-size: 12px;
  font-weight: 600;
  color: #d97706;
  background: #fef3c7;
  padding: 2px 8px;
  border-radius: var(--nm-radius-full);
}

.drawer-weak-chip {
  font-size: 11px;
  color: #dc2626;
  background: #fee2e2;
  padding: 2px 6px;
  border-radius: 4px;
  margin-right: 4px;
}

.q-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.q-no {
  font-weight: 700;
  font-size: 13.5px;
  color: var(--nm-text-primary);
}

.type-tag {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.7);
  color: var(--nm-text-secondary);
}

.score-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: var(--nm-radius-full);
  font-weight: 600;
}

.score-tag.normal { background: #dcfce7; color: #059669; }
.score-tag.needs-review { background: #fef3c7; color: #d97706; }
.score-tag.changed { background: #fee2e2; color: #dc2626; }

.q-detail {
  background: var(--nm-bg);
  border-radius: var(--nm-radius-md);
  box-shadow: var(--nm-shadow-inset);
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.q-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.q-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.q-col {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.q-label {
  font-size: 11.5px;
  color: var(--nm-text-light);
  font-weight: 600;
}

.q-content, .q-answer {
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: var(--nm-radius-sm);
  padding: 8px 12px;
  font-size: 13px;
  line-height: 1.6;
}

.q-answer.correct {
  background: #ecfdf5;
  border-color: #a7f3d0;
  color: #059669;
}

.q-feedback {
  font-size: 13px;
  color: var(--nm-text-regular);
  line-height: 1.6;
}

.point-row {
  display: flex;
  align-items: center;
  font-size: 12.5px;
  padding: 2px 0;
}

.test-pass-text {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--nm-success);
}

.q-modify-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: var(--nm-radius-md);
  border: 1px solid rgba(255, 255, 255, 0.9);
}

.modify-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--nm-text-primary);
}

.max-score-hint {
  font-size: 12px;
  color: var(--nm-text-light);
}

.action-bar {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(203, 213, 225, 0.4);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.action-hint {
  font-size: 12.5px;
  color: var(--nm-text-secondary);
}

.action-btns {
  display: flex;
  gap: 10px;
}

.cancel-btn {
  padding: 8px 18px;
}

.confirm-publish-btn {
  padding: 8px 20px;
  font-size: 13.5px;
}

.btn-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  display: inline-block;
}

@keyframes spin { to { transform: rotate(360deg); } }
</style>
