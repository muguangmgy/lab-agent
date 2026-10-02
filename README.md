# lab-agent

智能实验室预约系统：支持实验室/设备管理、预约审核，以及基于 LangGraph Agent 的多轮对话预约助手。

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3、Vite、Element Plus、Vue Router |
| 后端 | FastAPI、SQLAlchemy、LangGraph、LangChain |
| 数据 | MySQL、Redis（LangGraph Checkpointer）、Chroma（向量库） |

## 目录结构

```text
lab-agent/
├── README.md
├── docs/                 # 设计与改造说明
├── backend/              # FastAPI 后端
│   └── app/
│       ├── api/
│       ├── services/
│       │   └── agent/    # Agent / 会话 / Checkpointer
│       ├── models/
│       ├── schemas/
│       └── ...
└── frontend/             # Vue 前端
    └── src/
        ├── api/
        ├── views/        # 按业务分子目录（auth/system/lab/...）
        ├── components/
        ├── layouts/
        └── router/
```

## 环境依赖

- **MySQL**：创建库（如 `lab_agent`），字符集 `utf8mb4`
- **Redis**：供 LangGraph Checkpointer 使用（需支持 ReJSON / Redis Search 模块；建议 Docker 官方/兼容镜像，勿用缺模块的本机 Windows Redis）
- **Python** 3.10+（后端）
- **Node.js** 18+（前端）

## 后端启动

```sh
cd backend
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows；或 cp .env.example .env
# 编辑 .env：DATABASE_URL、JWT、LLM/Embedding、REDIS_URL 等

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动时会：建表、RBAC 种子、向量库预热、初始化 Redis Checkpointer、预约过期扫描。Redis 连不上会**阻止启动**。

## 前端启动

```sh
cd frontend
npm install
npm run dev
```

默认开发地址：`http://localhost:5173`（已在后端 CORS 白名单）。

生产构建：`npm run build`。

## 关键配置

| 文件 | 说明 |
|------|------|
| [`backend/.env.example`](backend/.env.example) | 后端环境变量模板（复制为 `backend/.env`） |
| [`frontend/.env.development`](frontend/.env.development) | 前端开发环境（如 API 代理基址） |

关键变量（后端）：`DATABASE_URL`、`REDIS_URL`、`JWT_SECRET_KEY`、`LLM_*`、`EMBEDDING_*`。

## 文档索引

| 文档 | 内容 |
|------|------|
| [`docs/项目结构规范改造.md`](docs/项目结构规范改造.md) | 目录规范与 views/agent 搬迁说明 |
| [`docs/Agent多轮对话与状态隔离.md`](docs/Agent多轮对话与状态隔离.md) | Agent 多轮对话、Redis Checkpointer、会话侧栏 |
| [`docs/用户角色菜单设计.md`](docs/用户角色菜单设计.md) | 用户 / 角色 / 菜单（RBAC）设计 |
