# 简历评审 Agent 分阶段计时设计

## 目标

在不改变简历评审 Agent 业务逻辑的前提下，为真实运行测试增加分阶段墙钟计时，并在测试进程控制台展示结果。

需要统计：

- PDF 简历文本提取。
- LLM 简历结构化提取。
- 六维度并行评审的整体墙钟时间。
- 六个维度各自的评审时间。
- 问题诊断。
- 问题总结。
- 从文本提取开始到问题总结结束的 Agent 总时间。

## 已确认的真实流程

`backend/agents/resume/graph.py` 定义的主流程为：

```text
upload_to_minio（本地模式跳过）
→ download_pdf（本地模式跳过）
→ extract_text
→ extract_structured
→ run_six_dimensions
→ diagnose_issues
→ generate_summary
→ save_results
```

除 `run_six_dimensions` 内部使用 `asyncio.gather()` 并行评审六个维度外，其余节点串行执行。

## 计时口径

- 使用 `time.perf_counter_ns()`，避免系统时间调整影响结果。
- 统一在展示时换算为毫秒，保留两位小数。
- 阶段时间覆盖该阶段的完整真实执行过程，包括 Prompt 组装、LLM 请求、结构化解析、重试和重试等待。
- 单维度时间分别覆盖各自协程的完整执行过程。
- `six_dimensions` 整体时间为六个并发任务从启动到全部结束的墙钟时间；它接近最慢维度耗时，而不是六项耗时之和。
- Agent 总时间从 `extract_text` 开始，到 `generate_summary` 返回结束，不包含 API 上传、轮询和数据库持久化。

## 方案

### 1. 上下文隔离的计时采集器

新增 `backend/agents/resume/timing.py`：

- 使用 `ContextVar` 保存当前异步任务上下文中的采集器。
- 未开启计时会话时，生产调用只进行一次轻量的上下文读取，不保存数据、不打印计时日志。
- 开启计时会话时，用同步上下文管理器记录阶段耗时。
- `asyncio.gather()` 创建的六个任务继承同一个采集器上下文，因此能分别记录六个维度。
- 计时上下文不写入 `ResumeState`，避免改变 LangGraph 状态契约。
- 不修改函数返回值和异常传播行为。

采集键固定为：

```text
extract_text
extract_structured
six_dimensions
dimension.project_depth
dimension.tech_match
dimension.expression
dimension.structure
dimension.quantification
dimension.authenticity
diagnose_issues
generate_summary
total
```

### 2. 最小业务代码插桩

仅修改 `backend/agents/resume/nodes.py`：

- 对 `extract_text_node`、`extract_structured_node`、`run_six_dimensions_node`、`diagnose_issues_node`、`generate_summary_node` 添加计时装饰器。
- 在 `review_one_dimension()` 外围添加单维度计时上下文。
- 不修改 Prompt、LLM 类型、参数、重试次数、退避时间、降级结果、评分权重、并发方式和返回结构。
- 不修改 `graph.py`、API、数据库表、前端或持久化数据格式。

### 3. 真实测试模块

新增 `scripts/manual_tests/benchmark_resume_agent.py`：

- 默认使用项目内 `samples/sample1.pdf`。
- 支持 `--file <PDF路径>` 指定其他简历。
- 把输入 PDF 复制到系统临时目录，防止任何测试清理逻辑影响原文件。
- 依次调用生产代码中的真实节点，严格保持主图顺序，执行到 `generate_summary` 为止。
- 调用真实 PDF 解析器、真实 DeepSeek LLM 和真实六维度并发逻辑，不使用性能数据 Mock。
- 不调用 `save_results_node`，因此不连接数据库、不新增审查记录、不删除用户数据。
- 成功后打印阶段耗时表、六维度耗时表、最慢维度和 Agent 总耗时。
- 失败时保留原始异常并清理临时 PDF。

示例输出：

```text
简历评审 Agent 真实耗时
----------------------------------------
简历文本提取             42.18 ms
简历结构化提取        12483.56 ms
六维度并行总耗时      18732.40 ms
  项目深度             9211.43 ms
  技术匹配度          10654.22 ms
  表达规范性           8432.10 ms
  简历结构            18731.90 ms
  量化程度             7994.17 ms
  真实可信度           8891.34 ms
问题诊断              15620.31 ms
问题总结               9034.25 ms
----------------------------------------
Agent 总耗时          55913.42 ms
最慢维度：简历结构
```

数值仅用于说明格式，实际结果以真实运行输出为准。

## 自动化验证

新增 `tests/resume/test_timing.py`，使用短时异步函数验证计时设施本身：

- 未开启计时会话时，被装饰函数的返回值不变。
- 开启计时会话时，记录名称和非负耗时。
- 被装饰函数抛出异常时，异常类型和消息不变，同时仍记录耗时。
- 多个并发计时区间能够分别写入，不互相覆盖。

真实性能测试不对毫秒值设置上下限，因为网络和模型响应时间天然波动；只检查所有必需计时项均存在且非负。

## 安全与影响边界

- 不读取、输出或写入 `.env.local` 内容。
- 不打印 API Key、登录令牌、简历正文或结构化简历内容。
- 不修改原 PDF。
- 不写数据库。
- 不修改正式 API 返回值。
- 不改变任何 Agent 业务分支或结果。
- 当前项目目录不是 Git 仓库，因此无法提交设计文档或代码 commit。

## 验收标准

1. 自动化计时测试先失败，再在实现后通过。
2. 简历评审相关现有可运行测试不因插桩失败。
3. 真实测试模块能够使用 `samples/sample1.pdf` 跑完整个评审分析过程。
4. 控制台展示五个主要阶段、六个维度、六维度墙钟时间和总时间。
5. 正式调用未开启计时会话时，不产生计时输出和额外状态字段。
