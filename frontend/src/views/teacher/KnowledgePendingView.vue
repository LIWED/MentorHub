<template>
  <div class="knowledge-pending-page">
    <div class="nm-card pending-card">
      <div class="card-header">
        <div class="header-icon-box">
          <span class="header-icon">📚</span>
        </div>
        <div>
          <h3 class="card-title">知识库待补充清单</h3>
          <p class="card-subtitle">AI 在问答与阅卷过程中未命中或低置信度的专业知识点，将自动归集至此处待教师补充</p>
        </div>
      </div>

      <div class="empty-placeholder">
        <div class="placeholder-icon-box">
          <span class="placeholder-icon">🌱</span>
        </div>
        <h4 class="placeholder-title">知识库自动扩充模块正在构建中</h4>
        <p class="placeholder-sub">
          未来将支持：一键从学员提问生成知识条目、PDF/Markdown 教案批量解析向量化、与知识图谱自动对齐。敬请期待！
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.knowledge-pending-page {
  max-width: 920px;
  margin: 0 auto;
  animation: pop-in 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.pending-card {
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

.empty-placeholder {
  padding: 60px 20px;
  text-align: center;
}

.placeholder-icon-box {
  width: 72px;
  height: 72px;
  border-radius: var(--nm-radius-xl);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-flat);
  border: var(--nm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 18px;
}

.placeholder-icon {
  font-size: 36px;
  animation: float-gentle 3s ease-in-out infinite;
}

.placeholder-title {
  margin: 0 0 8px;
  font-size: 17px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

.placeholder-sub {
  margin: 0 auto;
  max-width: 500px;
  font-size: 13px;
  color: var(--nm-text-secondary);
  line-height: 1.6;
}
</style>
