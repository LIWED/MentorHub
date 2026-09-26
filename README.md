# MentorHub

> 基于 LangGraph 构建的教育场景多智能体辅助平台，覆盖课程知识问答、试卷批改、简历评审与模拟面试。

MentorHub 采用 **FastAPI + LangGraph + Vue 3** 的前后端架构。后端将不同教学任务拆分为独立 Agent，并通过统一的 Orchestrator 进行调用与编排；其中课程问答模块实现了完整的 RAG 检索链路，简历评审模块实现了多维并行评审与结构化诊断。

## 核心功能

| 模块 | 主要能力 | 关键实现 |
| --- | --- | --- |
| **KnowFlow · 课程知识问答** | 课程知识库问答、通用问题处理、联网搜索兜底、多轮上下文 | Query Rewrite、SINGLE/BROAD/ITERATIVE、HyDE、Hybrid Retrieval、BGE Rerank、Evidence Sufficiency、Gap Retrieval、MCP Web Search、Memory |
| **Document Ingestion · 知识入库** | Markdown / PDF / 图片 / Office / HTML 等文档解析、结构化入库、图片增强、代码感知分块 | Parser Registry、MinerU 独立环境、MarkdownImageResolver、HTML Image Enrichment、Code-aware Chunking、BGE-M3 + BM25 |
| **Knowledge Management · 知识库管理** | 管理员创建课程、上传多文件/完整文件夹、查看解析状态并补充资料 | Course → Document → Chunk、相对路径保留、sitemap 识别、异步入库、重新解析/删除 |
| **Exam · 智能试卷批改** | 客观题、简答题、代码题自动批改，薄弱点分析，教师复核 | 三轨并行批改、LLM 结构化评分、低置信度人工复核、HitL |
| **ResumePilot · 简历评审** | PDF 简历解析、六维度评分、问题诊断、改进建议 | Structured Output、`asyncio.gather` 并行评审、Think → Diagnose、加权评分 |
| **Interview · 模拟面试** | 多阶段技术面试、回答评价、追问与最终报告 | LangGraph 状态流转、分阶段对话、回答评估、会话记忆 |
| **System Settings · 管理员设置** | 在线调整 QA 检索参数、LLM 与 Web Search 配置 | Runtime Settings、Admin-only API、热更新、API Key 仅返回配置状态 |

---

## 1. KnowFlow：课程知识问答 RAG Agent

KnowFlow 是 MentorHub 中的课程知识问答模块。它不是固定走一条 RAG 链，而是先判断问题类型，再选择对应的检索策略。

### 查询路由

QA Agent 首先将问题区分为：

- **General**：通用问题，直接由 LLM 回答；需要实时信息时可调用 Web Search。
- **Specialized**：课程或专业知识问题，进入 RAG 检索链路。

对于 Specialized Query，先执行 **Query Rewrite** 补全多轮对话中的指代与省略，再由 Structural Router 判断检索结构：

- **SINGLE**：单一信息需求，直接使用 Rewrite Query 检索。
- **BROAD / Multi Query**：多个可在检索前独立拆分的角度，最多生成 3 个子 Query 并行检索，再合并去重。
- **ITERATIVE**：存在前后依赖的信息需求，先规划最多 3 个逻辑问题，再根据上一阶段证据展开下一阶段 Query，最多进行 3 轮受控依赖检索。

**HyDE 不再作为一级 Query Type。** SINGLE / BROAD / ITERATIVE 完成第一次检索后统一进入 Retrieval Quality Gate；如果相关性不足，则生成 hypothetical document 做第二次检索，并将 Direct Retrieval 与 HyDE Retrieval 结果合并、去重后重新用真实 Query 做 Rerank。HyDE 后若相关性仍不足，再根据联网开关进入 Web Search 或 LLM Direct；如果相关性通过，则进入独立的 **Evidence Sufficiency Gate**，证据不完整时只针对缺失信息执行 Gap Retrieval。

其中 **BROAD / Multi Query** 解决“问题结构需要并行拆分”，**ITERATIVE** 解决“后续问题依赖上一轮证据”，而 **HyDE** 解决“Query 与知识库文档表达不匹配导致的低质量检索”，三者职责分离。

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
                              Candidate Pool
                                    │
                            BGE Reranker
                                    │
                           Evidence Top-K
                                    │
                    Relevance Gate → Sufficiency
```

- Embedding：**BGE-M3**
- Dense：负责语义相似度召回。
- BM25：应用侧使用 Jieba 分词并计算 BM25 权重，写入 Milvus Sparse Vector 完成关键词召回。
- Vector DB：**Milvus**
- Fusion：`WeightedRanker(0.7, 0.3)`，Dense / BM25 权重分别为 0.7 / 0.3。
- Reranker：本地配置模型优先（默认路径 `models/reranker/bge-reranker-large`），本地权重不可用时回退到 **BAAI/bge-reranker-v2-m3**。
- Candidate Pool：运行时默认 **SINGLE=20、HyDE=20、BROAD=每个子 Query 10、ITERATIVE=每个展开 Query 12**。
- Evidence Window：Reranker 默认保留 **Top 6**；真正送给生成模型的 Final Context 默认保留 **Top 3**。

当前把 **相关性（Relevance）** 与 **证据充分性（Sufficiency）** 分开处理：Reranker Top-1 分数负责判断“检索结果是否相关”，默认经验阈值为 **0.75**；相关性不足时先触发 HyDE，Direct Retrieval 与 HyDE Retrieval 合并后仍使用真实 Query 做全局 Rerank。相关性通过后，再由 Sufficiency Judge 判断“当前证据是否足够回答”；若不足，只针对缺失信息生成 Gap Query 并补搜。默认最多生成 **2 个 Gap Query**、执行 **2 轮 Gap Retrieval**，新旧证据合并去重后全局 Rerank，再次判断 Sufficiency。达到轮次上限仍不足时，再根据联网开关进入 Web Search 或有限证据生成路径。

以上 Recall / Rerank / Final Top-K、置信度阈值和 Gap Retrieval 上限均可在管理员 `/settings` 页面运行时修改，无需重启后端。

### 多轮记忆

QA / Interview 使用 LangGraph `MemorySaver` 保存会话状态，并实现：

- 最近 **10 轮**对话滑动窗口；
- 旧历史按批次进行增量摘要；
- 最近窗口始终保留原始消息，减少重复摘要与上下文膨胀。

---

## 2. 知识入库与文档解析

知识入库与在线 QA 解耦：复杂文档只在 **离线 ingestion 阶段**解析，不会把 MinerU 放进在线问答链路。

当前文档入口统一经过 `ParserRegistry`：

```text
File
 │
 ├─ .md / .markdown ──→ MarkdownParser
 ├─ .txt ─────────────→ TextParser
 └─ PDF / 图片 / Office / HTML / EPUB ...
                         ↓
                    MinerUParser
                         ↓
              structured_content / Markdown
                         ↓
                   LangChain Document
                         ↓
              Heading + Code-aware Chunking
                         ↓
                 BGE-M3 + BM25
                         ↓
                      Milvus
```

### MinerU 独立环境

MinerU 使用独立 Python 环境，通过 `scripts/mineru_parse_worker.py` 由主项目 subprocess 调用，避免 MinerU 的模型依赖与在线 RAG 环境中的 PyTorch / Transformers 版本相互污染。

推荐配置：

```text
EduAgent 主环境     → requirements.txt
MinerU 独立环境     → requirements-mineru.txt
```

PDF 若 MinerU 不可用或解析失败，会降级到 `LegacyPdfParser / PyPDFLoader`；其它富文档则保留显式错误，避免静默丢失复杂内容。

### Markdown / HTML 图片

`MarkdownImageResolver` 会识别 Markdown 图片与 HTML `<img>`；对于 `.html/.htm` 文件，MinerU Flash 先提取正文/标题/代码，再从原始 HTML 中解析图片引用并复用同一图片增强链路。

```markdown
![架构图](./images/rag.png)
<img src="./images/flow.png" alt="流程图" />
```

当前支持：

- 本地相对路径和 Windows 绝对路径；
- HTTP / HTTPS 图片下载；
- 同一图片重复引用去重；
- 图片优先使用 MinerU Advanced 解析，低价值结果可降级 OCR；
- 图片解析失败不会阻断整篇文档；
- Markdown 图片文本回填到原图片引用后；HTML 图片增强结果优先插回 MinerU 对应图片锚点附近；
- 过滤只有图片路径的低价值结果；
- 过滤明显由占位节点组成的错误 Mermaid。

回填后的文本形式类似：

```text
[图片内容：RAG 架构图]
...OCR / 表格 / 公式 / 可用图片文本...
[/图片内容]
```

> 当前 **普通截图、文本型图片、表格/公式图片** 已能进入知识库；复杂流程图和架构图的“节点连线关系”仍属于持续优化项。仓库中的 Ollama / Qwen3.5 图像理解脚本目前是实验工具，尚未作为正式默认 ingestion 能力接入。

### Code-aware Chunking

Markdown / HTML 解析后的 fenced code 不再和普通正文统一按 512 字符切分：

- 普通文本默认 `chunk_size=512`、`chunk_overlap=100`；
- 代码默认 `code_chunk_size=1200`、`code_chunk_overlap=120`；
- 保留代码围栏、语言标识与原始缩进；
- Python 优先按顶层 `def / async def / class` 边界切分；
- 只有单个函数本身超过代码窗口时，才继续从函数内部二次切分；
- Chunk 会携带 `chunk_type`、`code_language`、`code_part_index/total` 与 H1-H4 章节上下文。

### Contextual RAG

`scripts/build_knowledge_base.py` 保留了 Contextual RAG 上下文增强能力，但当前默认：

```python
use_context = False
```

原因是该步骤会为每个 Chunk 额外调用 LLM，成本较高。需要实验时可显式开启，不影响默认的 Parser → Chunk → BGE-M3 + BM25 → Milvus 链路。

---

## 3. ResumePilot：智能简历评审 Agent

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

## 4. Exam：智能试卷批改 Agent

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

## 5. Interview：模拟面试 Agent

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
| Language | Python 3.10+ |
| API | FastAPI 0.117.1 / Uvicorn |
| Agent Framework | LangChain 1.2.10 / LangGraph 1.0.9 |
| Structured Data | Pydantic 2 |
| Relational DB | PostgreSQL 15 / SQLAlchemy Async |
| Vector DB | Milvus 2.4.0 |
| Embedding | BGE-M3 |
| Sparse Retrieval | BM25 + Jieba |
| Reranker | BGE Reranker（本地模型优先，v2-m3 fallback） |
| Model Runtime | Transformers / Sentence Transformers / FlagEmbedding / PyTorch |
| Document Parsing | MinerU 4.x（独立环境）/ Markdown Parser / PyPDF fallback / pdfplumber / PyMuPDF / python-docx |
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
│  │  └─ v1/                   # auth / chat / qa / exam / resume / interview / settings
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
│  │  ├─ runtime_settings.py   # 管理员运行时检索 / API 设置
│  │  ├─ parsers/              # Parser Registry / MinerU / Markdown+HTML 图片解析
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
│  ├─ mineru_parse_worker.py   # 独立 MinerU 环境解析 Worker
│  ├─ test_document_extract.py # 文档解析独立 smoke test
│  ├─ manual_tests/
│  │  └─ test_document_ingestion.py # Parser + Chunking 人工质量检查
│  ├─ ollama_image_understanding_worker.py # 流程图视觉理解实验
│  ├─ seed_data.py
│  └─ seed_standard_exam.py
├─ tests/
│  ├─ parsers/
│  ├─ qa/
│  ├─ resume/
│  └─ interview/
├─ docker-compose.yml
├─ requirements.txt
├─ requirements-mineru.txt
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

主项目推荐使用 Python 3.11：

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

# 富文档 / 图片入库推荐配置独立 MinerU 环境
MINERU_PYTHON_EXECUTABLE=<MinerU 环境的 python 路径>
MINERU_TIER=basic
MINERU_OUTPUT_ROOT=./data/mineru
MINERU_TIMEOUT_SECONDS=900
# 国内模型下载可配置：
MINERU_MODEL_SOURCE=modelscope
```

### 4. 配置 MinerU 入库环境

复杂 PDF、图片、Office、HTML 等富文档推荐单独创建 MinerU 环境。MinerU 不建议直接安装进 MentorHub 主环境。

```bash
conda create -n mentorhub-mineru python=3.12 -y
conda activate mentorhub-mineru
pip install -r requirements-mineru.txt
```

然后把该环境的 Python 路径写入 `.env.local`：

```ini
# Windows 示例
MINERU_PYTHON_EXECUTABLE=F:\path\to\envs\mentorhub-mineru\python.exe
```

Markdown / TXT 不依赖 MinerU；PDF 在 MinerU 不可用时仍有文本层 fallback，但扫描 PDF、图片和复杂版面建议使用 MinerU。

### 5. 启动基础设施

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

### 6. 初始化 Milvus

```bash
python scripts/init_milvus.py
```

如需测试数据，可按需执行：

```bash
python scripts/seed_data.py
python scripts/seed_standard_exam.py
```

### 7. 导入知识库文档

当前 `scripts/build_knowledge_base.py` 通过脚本底部常量配置导入参数。首次使用前修改：

```python
FILE_PATH = r"<PDF / HTML / Markdown / Office 文档路径>"
COURSE_ID = "<课程 UUID>"
DOCUMENT_ID = None
TENANT_ID = "tenant_default"
USE_CONTEXT = False
```

然后执行：

```bash
python scripts/build_knowledge_base.py
```

入库阶段会先经过 Parser Registry。Markdown 会保留标题结构并解析图片引用；PDF / 图片 / Office / HTML 等复杂文档优先交给 MinerU。HTML 会额外解析原始 `<img>` 引用并复用图片增强链路；Markdown / HTML 中的 fenced code 会进入 Code-aware Chunking。解析后的内容统一包装为 LangChain `Document(page_content + metadata)`，再进行 BGE-M3 Dense 编码和 BM25 稀疏权重构建。

当前默认关闭 Contextual RAG，避免为每个 chunk 额外调用 LLM 产生较高成本。需要时可显式设置 `USE_CONTEXT=True` 开启上下文增强。

如只想人工检查 **Parser + Chunking** 质量，不执行 Embedding / BM25 / Milvus，可使用：

```bash
python scripts/manual_tests/test_document_ingestion.py "<文档路径>"
```

常用参数：

```bash
# 完整解析文本
python scripts/manual_tests/test_document_ingestion.py "<文档路径>" --full-text

# 完整文本 + 全部 Chunk
python scripts/manual_tests/test_document_ingestion.py "<文档路径>" --full-text --full-chunks --max-chunks 0
```

Windows 下若通过 Conda 执行并出现中文输出乱码，建议禁用 Conda 的 stdout 捕获：

```powershell
conda run --no-capture-output -n EduAgent python scripts\manual_tests\test_document_ingestion.py "<文档路径>" --full-text
```

### 8. 启动后端

在项目根目录执行：

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

API 文档：

```text
http://localhost:8000/docs
```

### 9. 启动前端

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
/api/v1/settings
/api/v1/knowledge
```

项目同时挂载两个 MCP 子应用：

```text
/mcp/kb
/mcp/web-search
```

分别用于知识库能力和联网搜索能力的标准化接入。

---

## 测试

Parser / 文档入库与 QA Retrieval：

```bash
pytest tests/parsers tests/qa -q
```

完整后端回归：

```bash
python -m pytest tests -q
```

人工检查任意文档的最终解析文本与 Chunk：

```bash
python scripts/manual_tests/test_document_ingestion.py "<文档路径>" --full-text --full-chunks --max-chunks 0
```

ResumePilot：

```bash
pytest tests/resume -q
```

模拟面试相关回归：

```bash
pytest tests/interview -q
```

此外，`backend/api/v1/` 下保留了部分业务 E2E 验证脚本，可用于单独检查 QA、Exam、Resume、Interview 等链路；GitHub CI 会执行后端测试、前端构建与 Compose 配置检查。

---

## 当前实现说明

MentorHub 仍处于持续开发阶段。README 以当前仓库代码为准，重点展示已经落地的 Agent Workflow、RAG 检索链路与工程结构，不将规划中的能力写成已完成功能。

当前几个需要特别区分的边界：

- **Contextual RAG**：代码保留，但默认关闭，只在需要时显式开启；
- **MinerU**：只用于离线知识入库，不进入在线 QA 请求链路；
- **Markdown / HTML 图片**：已进入正式入库链路，优先 Advanced 图像解析，低价值结果可降级 OCR；源图片不存在时明确记录失败，不生成伪造描述；
- **Code-aware Chunking**：Markdown / HTML 代码块使用独立的更大窗口，并保留代码围栏、缩进、语言与章节信息；
- **Runtime Settings**：管理员可热更新 QA Top-K、置信度、Gap Retrieval、LLM 与 Web Search 配置；当前使用本地 `.runtime_settings.json` overlay，适合单实例部署；
- **复杂流程图 / 架构图**：节点关系恢复仍在优化，`scripts/ollama_image_understanding_worker.py` 属于实验代码，目前未作为默认生产能力接入；
- **Parent-Child Retrieval**：当前没有启用，现阶段使用 Heading/Code-aware Chunking + Hybrid Retrieval + Rerank + Sufficiency/Gap Retrieval。

如果运行环境、模型或基础设施配置发生变化，请优先检查：

- `.env.example`
- `backend/config.py`
- `backend/core/llm_factory.py`
- `docker-compose.yml`

---

## License

本项目主要用于学习、课程实践与 AI Agent / RAG 工程研究。
