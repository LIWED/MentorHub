# MentorHub

> 基于 LangGraph 构建的教育场景多智能体辅助平台，覆盖课程知识问答、试卷批改、简历评审与模拟面试。

MentorHub 采用 **FastAPI + LangGraph + Vue 3** 的前后端架构。后端将不同教学任务拆分为独立 Agent，并通过统一的 Orchestrator 进行调用与编排；其中课程问答模块实现了完整的 RAG 检索链路，简历评审模块实现了多维并行评审与结构化诊断。

## 核心功能

| 模块 | 主要能力 | 关键实现 |
| --- | --- | --- |
| **KnowFlow · 课程知识问答** | 课程知识库问答、通用问题处理、联网搜索兜底、多轮上下文 | Query 分类、Query Rewrite、HyDE、Multi Query、Hybrid Retrieval、BGE Rerank、MCP Web Search、Memory |
| **Exam · 智能试卷批改** | 客观题、简答题、代码题自动批改，薄弱点分析，教师复核 | 三轨并行批改、LLM 结构化评分、低置信度人工复核、HitL |
| **ResumePilot · 简历评审** | PDF 简历解析、六维度评分、问题诊断、改进建议 | Structured Output、`asyncio.gather` 并行评审、Think → Diagnose、加权评分 |
| **Interview · 模拟面试** | 多阶段技术面试、回答评价、追问与最终报告 | LangGraph 状态流转、分阶段对话、回答评估、会话记忆 |

---

## 1. KnowFlow：课程知识问答 RAG Agent

KnowFlow 是 MentorHub 中的课程知识问答模块。它不是固定走一条 RAG 链，而是先判断问题类型，再选择对应的检索策略。

### 查询路由

QA Agent 首先将问题区分为：

- **General**：通用问题，直接由 LLM 回答；需要实时信息时可调用 Web Search。
- **Specialized**：课程或专业知识问题，进入 RAG 检索链路。

对于 Specialized Query，会进一步选择不同策略：

- **Precise Retrieval**：问题表达清晰时直接检索。
- **Query Rewrite**：结合会话历史补全指代、省略信息。
- **HyDE**：对语义模糊的问题生成 hypothetical document，再用于检索。
- **Multi Query**：对宽泛问题拆出多个查询，提高召回覆盖率。

### Hybrid Retrieval

当前代码中的混合检索方案为：

```text
Query
        │
        ├── BGE-M3 Dense Vector ──┐
        │                         ├── Milvus Hybrid Search
        └── BM25 Sparse ──────────┘
                            WeightedRanker(0.7, 0.3)
                                    │
                              Recall Top-K
                                    │
                         BGE-Reranker-v2-m3
                                    │
                              Rerank Top-K
                                    │
                           LLM Generate Answer
```

- Embedding：**BGE-M3**
- Dense：负责语义相似度召回。
- BM25：应用侧使用 Jieba 分词并计算 BM25 权重，写入 Milvus Sparse Vector 完成关键词召回。
- Vector DB：**Milvus**
- Fusion：`WeightedRanker(0.7, 0.3)`，Dense / BM25 权重分别为 0.7 / 0.3。
- Reranker：**BGE-Reranker-v2-m3** Cross Encoder。
- Hybrid Recall：默认 Top 10。
- Rerank：默认保留 Top 3。

当 Reranker Top-1 置信度低于代码设定阈值时，QA Agent 可以进入 Web Search 兜底链路。

### 多轮记忆

QA / Interview 使用 LangGraph `MemorySaver` 保存会话状态，并实现：

- 最近 **10 轮**对话滑动窗口；
- 旧历史按批次进行增量摘要；
- 最近窗口始终保留原始消息，减少重复摘要与上下文膨胀。

---

## 2. ResumePilot：智能简历评审 Agent

ResumePilot 将简历处理拆成一条 LangGraph Workflow：

```text
PDF
 │
 ├─ Extract Text
 ├─ Structured Extraction
 ├─ Six-Dimension Review
 ├─ Think
 ├─ Diagnose Issues
 ├─ Generate Summary
 └─ Save Results
```

### 六维度并行评审

当前实现包含六个评审维度：

- 项目深度
- 技术匹配度
- 表达规范性
- 简历结构
- 量化程度
- 描述一致性

六个维度通过 `asyncio.gather` 并行调用模型，随后按照预设权重计算综合评分。

### Think → Diagnose

在生成正式问题清单之前，系统先进行一次宏观分析，识别：

- 重复或相互关联的问题；
- 多个表面问题背后的共同原因；
- 应优先解决的核心问题。

然后再通过 Structured Output 生成结构化诊断结果和改进建议，减少直接逐条诊断带来的重复与碎片化。

---

## 3. Exam：智能试卷批改 Agent

Exam Agent 将题目按类型拆成三条批改轨道，并并行执行：

```text
                ┌─ 客观题：规则匹配
试卷解析 ───────┼─ 简答题：LLM 语义评分
                └─ 代码题：LLM 代码质量评估
                         │
                    聚合批改结果
                         │
                    薄弱知识点分析
                         │
                     教师复核 HitL
                         │
                       发布结果
```

其中：

- 单选、多选、判断题优先使用确定性规则评分；
- 简答题通过结构化 LLM 进行语义评分；
- 代码题由 LLM 根据题目、参考答案与学生代码进行评价；
- 低置信度结果会标记 `needs_review`，交由教师复核；
- 最后根据错题与知识标签生成薄弱点分析。

---

## 4. Interview：模拟面试 Agent

Interview Agent 使用 LangGraph 管理面试状态，主要流程包括：

```text
Load Context
    ↓
Check Stage
    ↓
Evaluate Answer
    ↓
Generate Response / Follow-up
    ↓
Save Memory
    ↓
Generate Final Report
```

系统可以根据当前面试阶段生成问题、评价回答并继续追问，在结束后生成面试报告并保存结果。

---

## Agent 编排

四个业务 Agent 由 `backend/core/orchestrator.py` 提供统一调用入口。

当前支持：

- **Single Agent**：直接调用指定 Agent；
- **Pipeline**：多个 Agent 串联执行；
- 当前已定义 `job_preparation` Pipeline：`Resume → Interview`。

每个 Agent 内部仍保持独立的 State 与 LangGraph Workflow，避免不同业务状态相互污染。

---

## 技术栈

### Backend

| 类型 | 技术 |
| --- | --- |
| Language | Python 3.11 |
| API | FastAPI 0.117.1 / Uvicorn |
| Agent Framework | LangChain 1.2.10 / LangGraph 1.0.9 |
| Structured Data | Pydantic 2 |
| Relational DB | PostgreSQL 15 / SQLAlchemy Async |
| Vector DB | Milvus 2.4.0 |
| Embedding | BGE-M3 |
| Reranker | BGE-Reranker-v2-m3 |
| Model Runtime | Transformers / Sentence Transformers / FlagEmbedding / PyTorch |
| Document Parsing | pdfplumber / PyMuPDF / python-docx |
| Tool Protocol | MCP |

LLM 调用统一通过 `backend/core/llm_factory.py` 管理，并使用 OpenAI-compatible 接口进行模型接入。

### Frontend

- Vue 3
- TypeScript
- Vite
- Element Plus
- Pinia
- Axios
- Markdown-It
- Highlight.js

---

## 项目结构

```text
MentorHub/
├─ backend/
│  ├─ main.py                  # FastAPI 入口
│  ├─ config.py                # 环境配置
│  ├─ api/
│  │  └─ v1/                   # auth / chat / qa / exam / resume / interview
│  ├─ agents/
│  │  ├─ qa/                   # KnowFlow RAG Agent
│  │  ├─ exam/                 # 试卷批改 Agent
│  │  ├─ resume/               # ResumePilot
│  │  └─ interview/            # 模拟面试 Agent
│  ├─ core/
│  │  ├─ orchestrator.py       # Agent 编排
│  │  ├─ llm_factory.py        # LLM 统一工厂
│  │  ├─ knowledge_base.py     # BGE-M3 + Milvus Hybrid Retrieval
│  │  ├─ reranker.py           # BGE Reranker
│  │  ├─ query_classifier.py   # QA Query 二分类
│  │  ├─ memory.py             # 多轮上下文与摘要
│  │  └─ retry.py              # 重试 / 降级
│  ├─ mcp/
│  │  ├─ knowledge_base_server.py
│  │  └─ web_search_server.py
│  └─ db/
├─ frontend/
│  └─ src/
├─ scripts/
│  ├─ init_db.sql
│  ├─ init_milvus.py
│  ├─ build_knowledge_base.py
│  ├─ seed_data.py
│  └─ seed_standard_exam.py
├─ tests/
│  └─ resume/
├─ docker-compose.yml
├─ requirements.txt
└─ .env.example
```

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/LIWED/MentorHub.git
cd MentorHub
```

### 2. 创建 Python 环境

推荐使用 Python 3.11：

```bash
conda create -n mentorhub python=3.11 -y
conda activate mentorhub
pip install -r requirements.txt
```

> 当前仓库依赖文件名为 `requirements.txt`，请按仓库中的实际文件名安装。

### 3. 配置环境变量

Windows PowerShell：

```powershell
Copy-Item .env.example .env.local
```

Linux / macOS：

```bash
cp .env.example .env.local
```

至少需要根据本地环境配置：

```ini
DB_HOST=localhost
DB_PORT=5433
DB_NAME=your_db_name
DB_USER=your_db_user
DB_PASSWORD=your_db_password

MILVUS_HOST=localhost
MILVUS_PORT=19531

DEEPSEEK_API_KEY=your_api_key
JWT_SECRET_KEY=your_random_secret

# QA 联网搜索需要时配置
TAVILY_API_KEY=your_tavily_key
```

### 4. 启动基础设施

当前 `docker-compose.yml` 包含：

- PostgreSQL
- etcd
- MinIO（作为 Milvus 内部对象存储）
- Milvus
- Attu

启动：

```bash
docker compose --env-file .env.local up -d
```

### 5. 初始化 Milvus

```bash
python scripts/init_milvus.py
```

如需测试数据，可按需执行：

```bash
python scripts/seed_data.py
python scripts/seed_standard_exam.py
```

### 6. 导入知识库文档

当前 `scripts/build_knowledge_base.py` 通过脚本底部常量配置导入参数。首次使用前修改：

```python
FILE_PATH = r"<PDF 或 Markdown 文档路径>"
COURSE_ID = "<课程 UUID>"
DOCUMENT_ID = None
TENANT_ID = "tenant_default"
USE_CONTEXT = False
```

然后执行：

```bash
python scripts/build_knowledge_base.py
```

当前默认关闭 Contextual RAG，避免为每个 chunk 额外调用 LLM 产生较高成本。需要时可显式设置 `USE_CONTEXT=True` 开启上下文增强；之后再生成 BGE-M3 Dense 向量，并基于当前语料重建 BM25 稀疏权重后写入 Milvus。

### 7. 启动后端

在项目根目录执行：

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

API 文档：

```text
http://localhost:8000/docs
```

### 8. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认运行在：

```text
http://localhost:3000
```

---

## 本地服务端口

| 服务 | 端口 | 说明 |
| --- | ---: | --- |
| MentorHub Frontend | 3000 | Vue 3 / Vite |
| FastAPI | 8000 | REST / SSE / Swagger |
| PostgreSQL | 5433 | Docker 映射到容器 5432 |
| Milvus | 19531 | Docker 映射到容器 19530 |
| Attu | 30000 | Milvus 可视化管理界面 |

> 当前 Compose 中 etcd 与 MinIO 仅供 Milvus 容器内部访问，没有暴露宿主机端口。

---

## API 与 MCP

业务 API 统一挂载在 `/api/v1`：

```text
/api/v1/auth
/api/v1/chat
/api/v1/qa
/api/v1/exam
/api/v1/resume
/api/v1/interview
```

项目同时挂载两个 MCP 子应用：

```text
/mcp/kb
/mcp/web-search
```

分别用于知识库能力和联网搜索能力的标准化接入。

---

## 测试

当前仓库已有 ResumePilot 相关测试：

```bash
pytest tests/resume -q
```

此外，`backend/api/v1/` 下保留了 QA、Exam、Resume、Interview 的 E2E 验证脚本，可用于单独检查各业务链路。

---

## 当前实现说明

MentorHub 仍处于持续开发阶段。README 以当前仓库代码为准，重点展示已经落地的 Agent Workflow、RAG 检索链路与工程结构，不将规划中的能力写成已完成功能。

如果运行环境、模型或基础设施配置发生变化，请优先检查：

- `.env.example`
- `backend/config.py`
- `backend/core/llm_factory.py`
- `docker-compose.yml`

---

## License

本项目主要用于学习、课程实践与 AI Agent / RAG 工程研究。
