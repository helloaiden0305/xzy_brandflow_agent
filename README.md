# XZY BrandFlow Agent

企业宣传工作流平台，基于 FastAPI、Vue、LangGraph 和 PostgreSQL 构建，用于企业宣传内容生成、人工审核、状态持久化与历史任务恢复。

## 功能特性

- **AI 主题策划**: 根据宣传方向生成候选宣传主题
- **AI 初稿撰写**: 根据选定主题生成企业宣传初稿
- **Human-in-the-loop**: 支持人工选择主题与发布前审稿
- **传播素材生成**: 自动提取视觉摘要并生成传播素材
- **状态持久化**: 使用 PostgreSQL Checkpointer 持久化工作流状态
- **历史任务恢复**: 支持 thread_id 任务恢复和用户隔离
- **SSE 流式输出**: 展示节点执行过程、LLM 输出和节点指标

## 技术栈

- **Python 3.10+**
- **FastAPI** - 异步 Web 框架
- **Vue + Vite** - 前端应用
- **LangGraph 1.0+** - 工作流编排
- **PostgreSQL** - 数据持久化
- **SQLAlchemy** - 异步 ORM
- **Pydantic** - 数据验证

## 快速开始

### 1. 环境准备

确保本地已安装并运行 PostgreSQL：

```bash
psql -U postgres -c "CREATE DATABASE brandflow_db;"
```

### 2. 安装后端依赖

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env`，再配置数据库、LLM、图片生成和 JWT 参数。本项目不会上传本地 `.env`。

```env
DATABASE_URL=postgresql+asyncpg://postgres:your_password@localhost:5432/brandflow_db
POSTGRES_URI=postgresql://postgres:your_password@localhost:5432/brandflow_db
APP_NAME=XZY BrandFlow Agent
DEBUG=true
LLM_API_KEY=your_llm_api_key
LLM_BASE_URL=https://your-llm-base-url
LLM_MODEL=your_model
LLM_MODEL_FAST=your_fast_model
IMAGE_API_KEY=your_image_api_key
IMAGE_BASE_URL=https://your-image-base-url
IMAGE_MODEL=your_image_model
JWT_SECRET_KEY=change-me
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
```

本项目不内置 Mock LLM / Mock Image 数据。完整体验工作流需要配置 PostgreSQL、`LLM_API_KEY` 和 `IMAGE_API_KEY`。

如果只是验证登录、工作流启动、历史任务和状态恢复，需要 PostgreSQL 与 LLM 配置。缺少 `LLM_API_KEY` 时，AI 主题生成、宣传初稿生成、视觉摘要提取可能失败或返回空结果。缺少 `IMAGE_API_KEY` 时，后端基础服务仍可启动，但传播素材生成不可用，实际调用图片生成时会返回清晰错误。

### 4. 启动后端服务

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API 文档地址: http://localhost:8000/docs

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev
```

## API 示例

### 启动宣传任务

```bash
POST /api/v1/workflow/start
Content-Type: application/json

{
    "topic_direction": "技术成果宣传"
}
```

**响应示例:**

```json
{
    "thread_id": "1_550e8400-e29b-41d4-a716-446655440000",
    "status": "topics_generated",
    "generated_topics": [
        "年度技术成果回顾",
        "研发团队创新实践",
        "产品能力升级发布"
    ],
    "message": "宣传任务已启动，请选择一个主题继续"
}
```

### 恢复任务 - 选择主题

```bash
POST /api/v1/workflow/resume/{thread_id}
Content-Type: application/json

{
    "action": "select_topic",
    "data": {
        "selected_topic": "年度技术成果回顾"
    }
}
```

### 恢复任务 - 审核通过

```bash
POST /api/v1/workflow/resume/{thread_id}
Content-Type: application/json

{
    "action": "approve"
}
```

### 恢复任务 - 审核驳回

```bash
POST /api/v1/workflow/resume/{thread_id}
Content-Type: application/json

{
    "action": "reject",
    "data": {
        "feedback": "请补充活动数据，并降低宣传语气"
    }
}
```

## 工作流程

```text
START
  |
  v
plan_topics          AI 生成候选宣传主题
  |
  v
human_select_topic   人工选择宣传主题
  |
  v
write_draft          AI 撰写宣传初稿
  |
  v
human_review         人工审核
  |
  +-- approved --> extract_visuals --> generate_images --> END
  |
  +-- rejected -----------------------> write_draft
```

## 项目结构

```text
app/
├── api/v1/              # 鉴权、工作流、图片接口
├── core/                # 配置、数据库、日志和中间件
├── graph/               # LangGraph 状态、节点、子图和工作流组装
├── models/              # 数据模型
├── services/            # LLM 与图片生成服务
└── main.py              # FastAPI 入口

frontend/
├── src/App.vue          # 前端主界面
├── src/api.js           # API 封装
└── src/style.css        # 页面样式
```

## 注意事项

1. 本地 `.env` 用于开发运行，不应提交到公开仓库。
2. LangGraph Checkpointer 会自动创建所需表结构。
3. 生成的传播素材默认保存在 `static/images/generated/`。

## License

MIT
