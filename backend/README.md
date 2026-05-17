# backend

FastAPI + SQLAlchemy + Alembic backend for CC Assistant.

See [../DESIGN.md](../DESIGN.md) for the data model and architectural decisions.

## 项目结构

```
backend/
├── app/
│   ├── config.py          # Pydantic Settings (env vars / defaults)
│   ├── db.py              # SQLAlchemy engine + Base + SessionLocal
│   ├── deps.py            # FastAPI dependencies (get_db)
│   ├── main.py            # FastAPI app entry
│   ├── models/            # SQLAlchemy ORM models
│   ├── schemas/           # Pydantic request/response schemas
│   ├── repositories/      # Data access layer (enforces invariants)
│   └── routers/           # FastAPI routers per domain
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/          # migration scripts
├── alembic.ini
├── requirements.txt
└── README.md
```

## 当前进度

- ✅ Slice 1：骨架 + `tags` CRUD
- ⬜ Slice 2：events + event_tags
- ⬜ Slice 3：recurrence_rules + task_instances + task_completion_log + 日历渲染
- ⬜ Slice 4：food_items + meal_templates
- ⬜ Slice 5：daily_meal_plans + day_type 推断 + 自动生成

## 首次环境搭建（Anaconda + pip）

PowerShell 里 `conda` 没在 PATH。两种解法二选一：

### 方法 A：一次性 `conda init`（推荐）

```powershell
& "C:\ProgramData\Anaconda3\Scripts\conda.exe" init powershell
```

然后**关闭并重新打开 PowerShell**，之后 `conda` 在所有 PowerShell 窗口都可用。

### 方法 B：用 Anaconda Prompt

从开始菜单找 **Anaconda Prompt**，所有 conda 命令在那里执行。

### 创建项目环境

```powershell
conda create -n cc_assistant python=3.11 -y
conda activate cc_assistant
cd backend
pip install -r requirements.txt
```

## 日常开发

每次新开终端先激活环境：

```powershell
conda activate cc_assistant
cd backend
```

### 应用数据库迁移

第一次跑、或同步了新的 migration 后：

```powershell
alembic upgrade head
```

这会在 `backend/` 下生成 `cc_assistant.db`（SQLite 文件，已 gitignore）。

### 启动开发服务器

```powershell
uvicorn app.main:app --reload
```

- API 根：http://localhost:8000
- 交互式接口文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

`--reload` 让代码改动自动重启。

### 验证 Tag CRUD 走通

在 http://localhost:8000/docs 里：

1. `POST /api/tags` 创建一个标签：

   ```json
   { "name": "工作", "color": "#4F46E5", "icon": "briefcase" }
   ```

2. `GET /api/tags` 应返回这个标签
3. `PATCH /api/tags/{id}` 改颜色
4. `DELETE /api/tags/{id}` 软删除
5. `GET /api/tags` 应返回空数组（软删除已生效，但 DB 里行还在）

也可用 DBeaver 连 `backend/cc_assistant.db` 直接看 `tags` 表，确认 `deleted_at` 被填上。

## 数据库管理

### 新建 migration

修改 `app/models/` 后：

```powershell
alembic revision --autogenerate -m "add events table"
```

检查生成的 `alembic/versions/xxxx_*.py`，必要时手改，然后：

```powershell
alembic upgrade head
```

### 重置数据库

```powershell
Remove-Item cc_assistant.db
alembic upgrade head
```

注意：仅适用于开发期。

## 设计约束（应用层强制）

详见 [../DESIGN.md](../DESIGN.md) §4.5。仓储层 (`app/repositories/`) 是约束的执行点：

- 软删除：所有 `list_*` / `get_*` 必须带 `deleted_at IS NULL` 过滤；删除走 `soft_delete` 而非 ORM `delete`
- 一次性字段（`completed_at` / `undone_at`）：仓储 update 时校验目标字段未被修改
- 只追加日志 (`task_completion_log`)：仓储不暴露 `update` / `delete`，只暴露 `append`
- 规则修改：`effective_date > today()` 强校验
- 时间统一存 UTC（数据库存 timezone-aware DateTime；应用层用 `datetime.now(timezone.utc)`）

新增 repository 时遵循这些约定。
