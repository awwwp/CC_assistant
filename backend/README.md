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
- ✅ Slice 2：`events` + `event_tags`（一次性事件 + 多标签）
- ✅ Slice 3：`recurrence_rules` + `task_instances` + `task_completion_log`（周期任务 / 打卡 / 日记）
- ⬜ Slice 4：日历渲染（RRULE 展开 + 合并 events）
- ⬜ Slice 5：food_items + meal_templates
- ⬜ Slice 6：daily_meal_plans + day_type 推断 + 自动生成

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

### 验证 CRUD 走通

在 http://localhost:8000/docs 里：

**Tags（slice 1）**

1. `POST /api/tags` 创建一个标签：

   ```json
   { "name": "工作", "color": "#4F46E5", "icon": "briefcase" }
   ```

2. `GET /api/tags` 应返回这个标签
3. `PATCH /api/tags/{id}` 改颜色
4. `DELETE /api/tags/{id}` 软删除
5. `GET /api/tags` 应返回空数组（软删除已生效，但 DB 里行还在）

**Events（slice 2）**

需要先有至少一个 tag。

1. `POST /api/events` 创建一个一次性事件：

   ```json
   {
     "title": "出发去旅游",
     "description": "上海 -> 杭州",
     "start_at": "2026-06-12T09:00:00Z",
     "end_at": "2026-06-15T18:00:00Z",
     "is_all_day": false,
     "tag_ids": [1]
   }
   ```

2. `GET /api/events` 返回所有事件（含完整 tag 信息）
3. `GET /api/events?start=2026-06-01T00:00:00Z&end=2026-06-30T23:59:59Z` 按时间范围查
4. `PATCH /api/events/{id}` 改 `tag_ids` 或时间。注意：`tag_ids` 字段省略 = 不动；传 `[]` = 清空；传新数组 = 整体替换
5. `DELETE /api/events/{id}` 软删除

也可用 DBeaver 连 `backend/cc_assistant.db` 直接看 `events` / `event_tags` 表。

**Recurrence rules / instances / completion log（slice 3）**

需要先有至少一个 tag。

1. `POST /api/rules` 创建一条周期任务规则：

   ```json
   {
     "title": "打羽毛球",
     "rrule": "FREQ=WEEKLY;BYDAY=SU",
     "dtstart": "2026-01-01",
     "time_of_day": "18:00:00",
     "duration_minutes": 90,
     "category": "exercise",
     "tag_id": 1
   }
   ```

   注意返回的 `series_id` —— 这是该任务跨规则版本的稳定身份。

2. `POST /api/rules/{rule_id}/instances/2026-05-10/checkin`，body 可省略或传 `{"notes":"打了三局"}` → 返回 `TaskInstanceRead`，`status` 应为 `completed`，`completed_at` 已填

3. 同一个日期再 checkin 一次 → **409 conflict**（一次性写入约束）

4. `POST /api/rules/{rule_id}/instances/2026-05-10/undo` → `status` 变 `withdrawn`，`undone_at` 已填

5. 再 undo 一次、或对未打卡的日期 undo → **409 conflict**

6. `GET /api/completion-log?series_id={步骤 1 返回的 series_id}` → 返回那条 5/10 的日记（即使你 undo 了，日记不会删）

7. `PATCH /api/rules/{rule_id}`：
   - 只改 `title`（纯外观） → 原地更新
   - 改 `rrule` 不传 `effective_from` → **422**
   - 改 `rrule` 且 `effective_from` ≤ today → **422**
   - 改 `rrule` 且 `effective_from` 是未来日期 → 切版本，返回新规则；旧规则的 `dtend` 被截断为 `effective_from - 1`，新旧规则同 `series_id`

8. `GET /api/rules/series/{series_id}` → 看到该 series 下所有版本（按 `dtstart` 升序）

注意 slice 3 还没有「日历渲染」接口（RRULE 在某月份的展开 + 合并 events）——那是 slice 4。当前阶段只能通过 `GET /api/rules/{id}/instances` 看已被触动的具体日期记录，还看不到未打卡的「该出现但还没动」的待办格子。

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
