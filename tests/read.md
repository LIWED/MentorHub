# MentorHub 前端优化接口说明（给 Gemini）

> 目标：只优化前端，不修改后端，不改变既有 API / SSE 协议。
>
> 项目根目录：F:\mygit\EduAgent
>
> 前端目录：F:\mygit\EduAgent\frontend

本文档根据当前前端代码整理。你可以重做 UI、布局、组件、状态展示和前端工程结构，但要把后端视为已经存在且不可修改的黑盒服务。

---

## 1. 修改边界

允许修改：

- frontend/src/views/**
- frontend/src/components/**
- frontend/src/stores/**
- frontend/src/composables/**
- frontend/src/router/**
- frontend/src/api/** 中的前端封装、类型声明和复用逻辑
- CSS / 响应式布局 / 动画 / Loading / Empty / Error 状态
- 必要的轻量前端组件和工具函数

不要修改：

- backend/**
- scripts/**
- 数据库结构
- LangGraph / RAG / Agent 业务逻辑
- API URL
- HTTP Method
- 请求字段名
- 后端响应字段语义
- SSE event type 和字段语义
- JWT 鉴权方式
- student / teacher / admin 权限语义

如果发现前端 TypeScript 类型与真实页面容错逻辑不一致，只在前端修正类型或增加适配层，不要要求修改后端。

---

## 2. 技术栈与验收

当前前端：

- Vue 3
- TypeScript
- Vite
- Vue Router
- Pinia
- Element Plus
- Axios
- Markdown-It
- Highlight.js
- UUID

修改完成后至少执行：

    cd F:\mygit\EduAgent\frontend
    npm ci
    npm run build

必须保证 vue-tsc 和 vite build 都通过。

---

## 3. API 基础约定

环境变量：

    VITE_API_BASE_URL=http://localhost:8000

它表示后端 origin，不要把 /api/v1 写进这个变量。

Axios 客户端：

    frontend/src/api/client.ts

Axios baseURL：

    VITE_API_BASE_URL + /api/v1

开发环境普通请求最终类似：

    http://localhost:8000/api/v1/...

生产环境如果前后端同域反代，VITE_API_BASE_URL 可以为空并使用相对地址。

### JWT

固定 localStorage key：

    edu-agent-token
    edu-agent-user

请求鉴权：

    Authorization: Bearer <token>

不要随意改这两个 localStorage key。

### Axios 全局错误语义

后端常见错误格式：

    {
      "detail": "错误说明"
    }

当前公共处理：

- 401：清除登录状态并跳 /login
- 403：权限不足
- 429：请求过于频繁
- >=500：服务异常
- 其他 detail：展示 detail

可以优化错误展示，但不要改变协议。

---

## 4. 登录、用户状态与权限

### POST /api/v1/auth/login

请求：

    {
      "username": "string",
      "password": "string"
    }

响应：

    {
      "access_token": "string",
      "token_type": "string",
      "expires_in": 0,
      "role": "student | teacher | admin",
      "user_id": "string"
    }

前端 UserInfo：

    {
      userId: string
      role: student | teacher | admin
      tenantId: string
      username?: string
    }

另有：

    GET /api/v1/auth/me

当前页面并未依赖其具体结构，不要自行假设字段。

---

## 5. 路由

必须保持兼容：

| Route | 页面 | 权限 |
| --- | --- | --- |
| /login | 登录 | Public |
| /dashboard | 首页 | 登录用户 |
| /chat | 统一 AI 助手 | 登录用户 |
| /qa | KnowFlow QA | 登录用户 |
| /exam | 试卷提交 | 登录用户 |
| /exam/:submissionId | 试卷结果 | 登录用户 |
| /resume | 简历上传 | 登录用户 |
| /resume/:reviewId | 简历报告 | 登录用户 |
| /interview | 模拟面试配置 | 登录用户 |
| /interview/:sessionId | 面试聊天 / 报告 | 登录用户 |
| /teacher/exam-review | 教师批改确认 | teacher / admin |
| /teacher/knowledge-pending | 知识库待补充 | teacher / admin |

权限规则：

- 未登录 -> /login
- student 不能进入 teacher 路由
- teacher / admin 显示教师菜单

---

# 6. QA / KnowFlow

相关文件：

    frontend/src/api/qa.ts
    frontend/src/views/qa/QAChatView.vue

## 6.1 非流式 QA

POST /api/v1/qa/chat

请求：

    {
      session_id: string
      course_id?: string | null
      message: string
    }

响应：

    {
      session_id: string
      answer: string
      answer_mode: rag | web_augmented | llm_direct | general
      confidence: number
      sources: string[]
      fallback_used: boolean
    }

当前主聊天页使用 SSE，但非流式接口仍需保持兼容。

## 6.2 QA 会话列表

GET /api/v1/qa/sessions

响应：

    {
      items: [
        {
          session_id: string
          title: string
          total_turns: number
          updated_at: string
        }
      ]
      total: number
    }

## 6.3 QA 历史

GET /api/v1/qa/sessions/:sessionId/history

响应：

    {
      session_id: string
      messages: [
        {
          role: user | assistant
          content: string
          created_at: string
          sources: string[]
          answer_mode?: string | null
          confidence?: number | null
        }
      ]
      summary: string | null
      total_turns: number
    }

## 6.4 删除 QA 会话

DELETE /api/v1/qa/sessions/:sessionId

新建但尚未发消息的 session 可能尚未落库，因此删除时 404 当前会被前端忽略。不要把这种 404 做成强阻断错误。

## 6.5 QA 流式主接口

POST /api/v1/qa/chat/stream

请求：

    {
      "session_id": "string",
      "message": "string",
      "enable_web_search": true
    }

enable_web_search 对应 QA 页 Web Search 开关，必须保留。

SSE 事件：

progress

    {
      "type": "progress",
      "stage": "正在执行的阶段"
    }

token

    {
      "type": "token",
      "content": "流式文本片段"
    }

content 需要按顺序拼接。

meta

    {
      "type": "meta",
      "answer_mode": "rag | web_augmented | llm_direct | general",
      "confidence": 0.91,
      "sources": ["..."],
      "fallback_used": false
    }

confidence 是 0~1，小数；当前 UI 乘 100 展示。

error

    {
      "type": "error",
      "message": "错误信息"
    }

QA 页面现有行为要保留：

- session ID 由前端生成：student_session_<uuid>
- 会话列表
- 新建 / 切换 / 删除
- 历史按需加载
- 流式期间禁止重复发送
- Enter 发送
- Shift+Enter 换行
- Markdown / 代码高亮
- sources
- Web Search 开关
- QAChatView 被 AppLayout 的 keep-alive 缓存

如果重构 Layout，不要无意移除 QA 的状态保留能力。

---

# 7. Unified Chat 统一 AI 助手

文件：

    frontend/src/views/UnifiedChatView.vue

POST /api/v1/chat/stream

请求：

    {
      "session_id": "unified_<userId>",
      "message": "用户输入"
    }

当前统一助手 session 固定为：

    unified_${userId}

用于同一用户复用一个统一 Agent thread。

## SSE 事件

routing_decision

    {
      type: routing_decision
      agent_type: string
      agent_display: string
      confidence: number
      reason: string
      execution_mode: string
    }

常见 agent_type：

    qa
    exam
    resume
    interview

execution_mode：

    single
    pipeline
    clarify

confidence 是 0~1；RoutingDecisionCard 自己转换成百分比。

progress

    {
      "type": "progress",
      "stage": "处理中..."
    }

token

    {
      "type": "token",
      "content": "文本片段"
    }

guidance

    {
      type: guidance
      message: string
      action_label?: string
      action_url?: string
    }

action_url 当前直接用于 Vue Router 跳转。

pipeline_plan

    {
      type: pipeline_plan
      title: string
      intro: string
      steps: [
        {
          step: number
          agent_type: string
          label: string
          desc: string
          action_label: string
          action_url: string
          tip: string
        }
      ]
    }

meta

    {
      type: meta
      answer_mode?: string
      confidence?: number
      sources?: string[]
    }

error

    {
      "type": "error",
      "message": "..."
    }

Unified Chat 重做视觉时必须继续承载：

- Routing Decision
- Pipeline Plan
- Guidance 跳转按钮
- Progress
- Token 流
- Markdown
- Sources
- Answer Mode

---

# 8. ResumePilot 简历审查

相关文件：

    frontend/src/api/resume.ts
    frontend/src/views/resume/*

## 8.1 上传简历

POST /api/v1/resume/upload

Content-Type：

    multipart/form-data

Form field：

    file

响应：

    {
      review_id: string
      status: string
      message: string
    }

现有约束：

- UI 只接受 PDF
- 前端限制 10MB
- 成功后跳转 /resume/:reviewId

## 8.2 获取审查结果

GET /api/v1/resume/reviews/:reviewId

响应：

    {
      review_id: string
      status: processing | done | failed
      error_msg?: string
      weighted_score?: number

      dimension_scores?: [
        {
          key: string
          dimension: string
          score: number
          weight: number
          issues: string[]
          suggestions: string[]
        }
      ]

      issues?: [
        {
          priority: high | medium | low
          dimension: string
          description: string
          location: string
          suggestion: string
        }
      ]

      summary?: {
        highlights: string[]
        core_improvements: string[]
        overall_comment: string
        fit_assessment: string
      }
    }

状态：

- processing：显示处理中并继续轮询
- done：展示完整报告
- failed：展示 error_msg

当前约每 5 秒轮询一次。

可以优化 Loading / Skeleton / Error，但不要依赖后端新增“百分比进度”字段。

## 8.3 简历历史

GET /api/v1/resume/reviews

响应：

    {
      items: [
        {
          review_id: string
          status: string
          created_at: string
          weighted_score?: number
        }
      ]
      total: number
    }

## 8.4 删除简历审查

DELETE /api/v1/resume/reviews/:reviewId

---

# 9. Exam 智能试卷批改

相关文件：

    frontend/src/api/exam.ts
    frontend/src/views/exam/*
    frontend/src/views/teacher/ExamReviewView.vue

## 9.1 学员提交

POST /api/v1/exam/submit

multipart/form-data：

    exam_id
    file

响应：

    {
      submission_id: string
      status: string
      message: string
    }

当前 UI：

- accept=.docx
- 文案写最大 20MB
- 当前前端代码并未真正检查 20MB

可以只在前端补 size validation，不需要后端配合。

## 9.2 学员提交历史

GET /api/v1/exam/my-submissions

响应：

    {
      items: [
        {
          submission_id: string
          exam_id: string
          exam_title: string
          status: string
          submitted_at: string
        }
      ]
    }

当前状态映射：

- published -> 已发布
- pending_review -> 等待教师确认
- ai_processing -> AI 批改中
- submitted -> 当前 UI 视为处理失败 / 需重新提交

## 9.3 学员查看状态 / 结果

GET /api/v1/exam/my-submissions/:submissionId

必须兼容两种返回阶段。

处理中可能只有：

    {
      submission_id: string
      status: string
    }

此时可能没有 pre_review_summary / weak_points / weak_points_summary。

完整结果结构：

    {
      submission_id: string
      student_id?: string
      status?: string

      pre_review_summary: {
        total_score: number
        full_score: number

        by_question: [
          {
            question_id: string
            question_no: number
            question_type: string
            full_score: number
            score: number
            content?: string
            student_answer: string
            correct_answer?: string
            ai_feedback: string
            needs_review: boolean

            point_results?: [
              {
                point_score: number
                point_desc: string
                earned: boolean
                missing?: string
              }
            ]

            test_cases_passed?: number
            test_cases_total?: number
            sandbox_skipped?: boolean
            quality_feedback?: string[]
            teacher_comment?: string
            final_score?: number
          }
        ]
      }

      weak_points: [
        {
          tag: string
          wrong_count: number
          total_count?: number
          question_nos?: number[]
          suggestion?: string
        }
      ]

      weak_points_summary: string
    }

重要：weak_points[].tag 字段叫 tag，不叫 knowledge_point。

当前 ExamResultView 大约每 8 秒轮询一次。

注意：api/exam.ts 当前 ReviewDetail 把 pre_review_summary 写得偏严格，但页面真实逻辑需要兼容“处理中只有 status”。如果优化类型，请在前端定义 union 或 optional 字段，不要要求后端改变处理中响应。

---

# 10. Teacher Exam 审核

仅 teacher / admin。

## 10.1 待审核列表

GET /api/v1/exam/pending-reviews

响应：

    {
      items: [
        {
          submission_id: string
          student_name: string
          exam_title: string
          submitted_at: string

          pre_review: {
            total_score: number
            full_score: number
            needs_review_count: number
          }

          weak_points: [
            {
              tag: string
              wrong_count: number
              total_count?: number
              question_nos?: number[]
              suggestion?: string
            }
          ]
        }
      ]
      total: number
    }

## 10.2 获取教师审阅详情

GET /api/v1/exam/submissions/:submissionId/review

使用完整 ReviewDetail。

教师页面依赖：

- question_id
- question_no
- question_type
- content
- student_answer
- correct_answer
- score
- full_score
- needs_review
- ai_feedback
- point_results
- test_cases_passed
- test_cases_total
- sandbox_skipped
- weak_points[].tag

## 10.3 确认 / 修改后发布

POST /api/v1/exam/submissions/:submissionId/confirm

请求：

    {
      action: approve | modify
      modifications: [
        {
          question_id: string
          new_score?: number
          comment?: string
        }
      ]
    }

无修改：

    {
      "action": "approve",
      "modifications": []
    }

有改分：

    {
      "action": "modify",
      "modifications": [
        {
          "question_id": "...",
          "new_score": 8,
          "comment": "教师批注"
        }
      ]
    }

响应：

    {
      submission_id: string
      status: string
      final_score: number
      full_score: number
      score_rate: number
      weak_points: Array
      weak_points_summary: string
    }

当前教师 UI 只提交真正改过分数的题目。不要改变该业务语义。

---

# 11. Interview 模拟面试

相关文件：

    frontend/src/api/interview.ts
    frontend/src/views/interview/*

## 11.1 开始面试

POST /api/v1/interview/sessions

请求：

    {
      target_position: string
      resume_review_id?: string | null
    }

响应：

    {
      session_id: string
      target_position: string
      status: string
      message: string
    }

message 是开场消息。

当前页面通过 Router history state 把 openingMessage 带到 /interview/:sessionId。

如果重构 Router，请保留等价行为。

## 11.2 非流式聊天

POST /api/v1/interview/sessions/:sessionId/chat

请求：

    {
      "message": "string"
    }

响应：

    {
      session_id: string
      reply: string
      current_stage: string
      total_turns: number
      is_finished: boolean

      report_summary?: {
        overall_score: number
        strengths: string[]
        improvements: string[]
      }
    }

当前主聊天页主要使用流式接口。

## 11.3 流式聊天

POST /api/v1/interview/sessions/:sessionId/chat/stream

请求：

    {
      "message": "string"
    }

SSE：

token

    {
      "type": "token",
      "content": "文本片段"
    }

done

    {
      type: done
      reply: string
      current_stage: string
      total_turns: number
      is_finished: boolean

      report_summary?: {
        overall_score: number
        strengths: string[]
        improvements: string[]
      }
    }

error

    {
      "type": "error",
      "message": "..."
    }

重要：部分后端路径可能不先发 token，而是直接在 done.reply 中携带整段回复。

所以前端必须同时支持：

    token -> token -> done

以及：

    done(reply=完整文本)

不要假设 done 前一定出现 token。

## 11.4 面试报告

GET /api/v1/interview/sessions/:sessionId/report

响应：

    {
      session_id: string
      target_position: string
      overall_score: number

      dimensions: [
        {
          dimension: string
          score: number
          comment: string
        }
      ]

      strengths: string[]
      improvements: string[]
      overall_comment: string
      recommended_topics: string[]
      next_step_advice: string
    }

页面行为：

- 面试结束后主动请求报告
- mounted 时也会检查报告是否已经存在，以恢复已结束面试

## 11.5 面试历史

GET /api/v1/interview/sessions

响应：

    {
      items: [
        {
          session_id: string
          target_position: string
          overall_score?: number
          status: string
          finished_at?: string
          created_at: string
        }
      ]
      total: number
    }

当前 UI 以 status === finished 判断已完成。

---

# 12. Dashboard / Layout 约束

Dashboard 入口：

- /chat
- /qa
- /exam
- /resume
- /interview

AppLayout 当前包括：

- 左侧 Sidebar
- 顶部用户信息 / Logout
- RouterView
- 路由加载进度条
- QAChatView keep-alive
- RouterView 子树错误恢复逻辑

视觉和布局可以重做，但不要无意移除登录退出、权限菜单、QA 状态保留等能力。

---

# 13. Chat / Markdown 组件

现有：

    components/chat/ChatBubble.vue
    components/chat/MarkdownRenderer.vue
    components/chat/RoutingDecisionCard.vue
    components/chat/PipelinePlanCard.vue

聊天需要继续支持：

- Markdown
- 代码块
- Highlight.js
- user / assistant 气泡
- sources
- 路由决策
- 多 Agent pipeline plan

视觉可以全部改。

---

# 14. 可以安全做的前端重构

## 14.1 抽 SSE 公共读取器

当前 SSE 解析分散在：

- QAChatView.vue
- UnifiedChatView.vue
- api/interview.ts
- composables/useSSEChat.ts

可以抽公共 SSE stream reader。

但三条链路事件 schema 不同，不能为了“统一”去要求后端统一 event。

另外 useSSEChat.ts 目前不是 QAChatView 的实际 source of truth，重构时以 QAChatView 真实调用为准。

## 14.2 统一 401 Logout

Axios 401 会调用 Pinia logout，但 QA / Unified Chat 的原生 fetch 当前直接清 localStorage。

可以前端抽公共 logout / unauthorized handler，使 Pinia + localStorage 同步。

后端仍保持 Bearer JWT。

## 14.3 Interview 报告请求去重

InterviewChatView 当前直接调用 client.get(.../report)，同时 interviewApi 已提供 getReport。

可以统一到 API 层，路径不要变。

## 14.4 Exam Response Type

建议把学生轮询中的状态响应和完整结果区分为前端 union，例如：

    ProcessingReview | CompletedReview

这是前端类型问题，不修改后端。

## 14.5 响应式布局

当前较明显的 Desktop-only 倾向：

- 固定 200px Sidebar
- el-col span=6 / 8 / 12 / 18
- 固定 max-width
- Chat 高度按桌面视口计算

可以重点增强：

- Laptop
- Tablet
- Mobile
- Sidebar 折叠 / Drawer
- Grid breakpoint
- Chat 输入区移动端适配
- 表格窄屏体验

---

# 15. 不可破坏的契约总表

鉴权：

    Authorization: Bearer <token>

localStorage：

    edu-agent-token
    edu-agent-user

API：

    /api/v1/auth/*
    /api/v1/qa/*
    /api/v1/chat/stream
    /api/v1/exam/*
    /api/v1/resume/*
    /api/v1/interview/*

QA SSE：

    progress
    token
    meta
    error

Unified Chat SSE：

    routing_decision
    progress
    token
    guidance
    pipeline_plan
    meta
    error

Interview SSE：

    token
    done
    error

API 边界继续使用 snake_case，例如：

    session_id
    review_id
    submission_id
    answer_mode
    fallback_used
    current_stage
    total_turns
    is_finished
    weak_points
    weak_points_summary
    target_position
    resume_review_id

前端内部 ViewModel 可以 camelCase，但发送 / 解析 API 时必须保持现有协议或显式转换。

---

# 16. 优化优先级

建议优先：

1. 统一 MentorHub 视觉语言
2. 优化 Sidebar / Header / Dashboard 信息层级
3. 统一 Loading / Empty / Error / Streaming 状态
4. 提升聊天区域和输入区体验
5. 改善 Resume / Exam / Interview 结果页可读性
6. 响应式布局
7. 抽重复组件
8. 抽重复 SSE / Auth 前端逻辑
9. 优化 TypeScript 类型
10. 控制包体积和无必要依赖

不要为了视觉效果破坏现有业务流程。

---

# 17. 人工验收核心链路

登录
    -> Dashboard

Dashboard
    -> Unified Chat
    -> QA
    -> Exam
    -> Resume
    -> Interview

student
    -> 不出现教师菜单
    -> 无法进入教师路由

teacher / admin
    -> 显示教师菜单
    -> 可进入 /teacher/exam-review

QA
    -> 加载会话
    -> 新建会话
    -> SSE progress / token / meta
    -> sources
    -> Web Search 开关
    -> 切换历史
    -> 删除会话

Unified Chat
    -> routing_decision
    -> progress
    -> token
    -> guidance
    -> pipeline_plan
    -> meta

Resume
    -> PDF 上传
    -> processing
    -> done / failed
    -> 历史列表
    -> 删除记录

Exam
    -> DOCX 上传
    -> 历史提交
    -> processing 状态容错
    -> 结果轮询
    -> published 结果

Teacher Exam
    -> 待审列表
    -> 打开详情
    -> 题目 / 答案 / AI 反馈
    -> 修改分数
    -> 发布

Interview
    -> 创建 session
    -> openingMessage
    -> SSE token
    -> SSE done
    -> done.reply 无 token 情况
    -> 结束面试
    -> 报告
    -> 历史记录

---

# 18. 给 Gemini 的最终要求

请只负责 MentorHub 前端优化。

后端、数据库、RAG、Agent、接口协议均视为不可修改。不要通过修改 backend 来解决 UI 问题，也不要要求后端为了前端重命名字段或新增接口。

可以重构前端 API 封装、组件和类型，但所有外部 API / SSE 契约必须保持兼容。

完成后：

1. 执行 npm run build。
2. 修复所有 TypeScript / Vite build 错误。
3. 不修改 backend/**。
4. 列出实际修改的前端文件。
5. 简述主要 UI / UX 改进。
6. 特别确认 QA、Unified Chat、Interview 三套 SSE 都没有被破坏。
