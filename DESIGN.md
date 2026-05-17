# DESIGN.md

> 面向开发者与 AI agent 的项目设计文档。用户面向说明见 [FEATURES.md](FEATURES.md)。
>
> **本文档为 v1 设计固化版本**。数据模型已锁定，后续修改需通过 PR 评审并在第 5 节追加决策记录。

## 1. 项目定位

个人使用的「日程 + 饮食」一体化 Web 应用。核心目标是替代散落在备忘录、日历、健身/饮食 app 中的工作流，为单一高强度脑力 + 运动用户提供统一的任务编排和饮食规划界面。

**当前阶段**：单用户、内网访问。
**未来阶段**：可能扩展为多用户、公网部署。架构上需为此预留空间，但当前不实现用户系统。

## 2. 架构总览

B/S 架构，前后端分离。

```
┌─────────────────┐    HTTPS/HTTP    ┌──────────────────┐
│  Browser (Vue)  │ ───────────────▶ │  Caddy (proxy)   │
│  桌面 / 移动竖屏 │                  └────────┬─────────┘
└─────────────────┘                           │
                                              ├──▶ 静态文件 (dist/)
                                              │
                                              └──▶ /api/* ──▶ FastAPI (uvicorn)
                                                                  │
                                                                  ▼
                                                              SQLite
                                                          (→ PostgreSQL)
```

整套服务以 Docker Compose 编排，宿主机通过 Tailscale 暴露给用户的其它设备。

## 3. 技术栈

### 前端
- **框架**：Vue 3 + TypeScript
- **构建**：Vite
- **状态管理**：Pinia
- **UI 库**：Element Plus 或 Naive UI（待选定）
- **日历组件**：FullCalendar 或 vue-cal（待选定）
- **RRULE 解析**：rrule.js
- **HTTP**：axios 或 fetch + 自封装
- **响应式**：必须适配桌面 + 手机竖屏

### 后端
- **框架**：FastAPI
- **ASGI 服务器**：uvicorn
- **ORM**：SQLAlchemy 2.0
- **数据库迁移**：Alembic
- **数据校验**：Pydantic（FastAPI 内置）
- **RRULE 解析**：python-dateutil
- **语言**：Python 3.11+

**选型理由**：FastAPI 学习曲线平、类型注解直接驱动接口文档（`/docs`）、Pydantic 自动校验；Python 生态便于未来接入 LLM 做饮食智能推荐。

### 数据库
- **当前**：SQLite（单文件、零运维）
- **迁移目标**：PostgreSQL（多用户/公网部署时切换）
- **抽象**：通过 SQLAlchemy 屏蔽差异
- **管理工具**：DBeaver（开发期人肉查表）；结构变更必须走 Alembic，不允许 GUI 改 schema

### 反向代理 / Web 服务器
- **Caddy**：发布前端静态文件 + 反向代理 `/api/*` 到 FastAPI；未来公网时自动 HTTPS

### 部署
- **容器化**：Docker + docker-compose
- **远程访问**：Tailscale（设备组虚拟内网，端到端加密、点对点直连）
- **宿主机**：用户家中常开机器（笔电/小主机），需配置开机自启
- **公网部署（未来）**：VPS + 域名 + Caddy 自动证书；docker-compose 文件复用

## 4. 核心数据模型（v1 已固化）

完整 schema 共 10 张表，分为事件、周期任务、饮食三个域。

### 4.1 总览

```
事件域：
  tags ── event_tags ── events

周期任务域：
  tags ── recurrence_rules ── task_instances
                │
                └── task_completion_log（append-only 日记）

饮食域：
  food_items ─┬─ meal_template_items ── meal_templates
              └─ daily_meal_items     ── daily_meal_plans
```

### 4.2 贯穿所有表的设计原则

1. **过去不可变**：任何修改/删除都不会改写已发生的事实
   - 手段：软删除（`deleted_at`）+ 规则截断（`dtstart`/`dtend`）+ 写时快照
2. **任务身份稳定**：同一概念上的任务用 `series_id`（UUID）唯一标识，规则版本变化不影响身份
3. **状态由时间戳推导，不冗余存 `status` 列**，避免数据不一致
4. **周期任务不预生成实例**：用 RRULE + 例外表，渲染时动态展开
5. **关键写入字段一次性**：撤销字段、日记记录只追加，禁止 UPDATE/DELETE
6. **时间统一存 UTC**，前端按本地时区渲染

### 4.3 表结构

#### `tags` — 标签字典

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | |
| `name` | TEXT UNIQUE NOT NULL | "旅行" / "健身" |
| `color` | TEXT NOT NULL | 十六进制色值 |
| `icon` | TEXT | 图标名 |
| `description` | TEXT | |
| `deleted_at` | TIMESTAMP | 软删除 |
| `created_at` | TIMESTAMP NOT NULL | |

#### `events` — 一次性事件

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | |
| `title` | TEXT NOT NULL | |
| `description` | TEXT | Markdown |
| `start_at` | TIMESTAMP NOT NULL | UTC |
| `end_at` | TIMESTAMP | UTC，可空 |
| `is_all_day` | BOOLEAN NOT NULL DEFAULT 0 | |
| `deleted_at` | TIMESTAMP | |
| `created_at` / `updated_at` | TIMESTAMP NOT NULL | |

INDEX `events_start_at` ON (`start_at`)

#### `event_tags` — 事件↔标签 多对多

| 字段 | 类型 |
|---|---|
| `event_id` | FK → `events(id)` ON DELETE CASCADE |
| `tag_id` | FK → `tags(id)` ON DELETE RESTRICT |
| PRIMARY KEY (`event_id`, `tag_id`) | |

#### `recurrence_rules` — 周期任务规则

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | |
| `series_id` | TEXT NOT NULL | UUID，同一任务跨版本共享 |
| `title` | TEXT NOT NULL | |
| `description` | TEXT | |
| `rrule` | TEXT NOT NULL | iCalendar RFC 5545 |
| `dtstart` | DATE NOT NULL | 该版本生效起始 |
| `dtend` | DATE | 该版本生效结束，NULL = 永久 |
| `time_of_day` | TIME | NULL = 全天任务 |
| `duration_minutes` | INTEGER | |
| `category` | TEXT | `work` / `exercise` / `personal` 等 |
| `tag_id` | FK → `tags(id)` | 单值 |
| `is_active` | BOOLEAN NOT NULL DEFAULT 1 | |
| `deleted_at` | TIMESTAMP | |
| `created_at` / `updated_at` | TIMESTAMP NOT NULL | |

INDEX `rules_series` ON (`series_id`), `rules_active_range` ON (`deleted_at`, `dtstart`, `dtend`)

#### `task_instances` — 周期任务实例状态（只存例外/打卡）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | |
| `rule_id` | FK → `recurrence_rules(id)` ON DELETE CASCADE | |
| `occurrence_date` | DATE NOT NULL | 实例对应日期 |
| `completed_at` | TIMESTAMP | **一次性写入** |
| `undone_at` | TIMESTAMP | **一次性写入** |
| `notes` | TEXT | |
| `override_title` | TEXT | 此次实例标题改写 |
| `override_time` | TIME | 此次实例时间改写 |
| `created_at` / `updated_at` | TIMESTAMP NOT NULL | |

UNIQUE (`rule_id`, `occurrence_date`), INDEX `instances_date` ON (`occurrence_date`)

**状态推导**（在应用层完成，不存 `status` 列）：

| `completed_at` | `undone_at` | 显示状态 |
|---|---|---|
| NULL | NULL | 待办 ⬜ |
| 非空 | NULL | 已完成 ✅ |
| 非空 | 非空 | 曾完成后撤销 ✅+删除线（终态） |

**关键约束**：
- `completed_at` 写入后**不可修改**
- `undone_at` 写入后**不可修改**
- 撤销操作只能在 `completed_at IS NOT NULL AND undone_at IS NULL` 时进行
- 撤销是**终态**，不可恢复（如需重新认定完成，须直接 DB 修复）
- UI 在写入 `undone_at` 前必须二次确认

#### `task_completion_log` — 完成日记（append-only）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | |
| `rule_id` | FK → `recurrence_rules(id)`（不级联） | 可指向已软删规则 |
| `series_id` | TEXT NOT NULL | 写时快照 |
| `occurrence_date` | DATE NOT NULL | |
| `completed_at` | TIMESTAMP NOT NULL DEFAULT now() | |
| `title_snapshot` | TEXT NOT NULL | 写时规则 title |
| `tag_color_snapshot` | TEXT | 写时 tag 颜色 |
| `category_snapshot` | TEXT | 写时规则 category |
| `notes` | TEXT | |

INDEX `log_date` ON (`occurrence_date`), `log_series` ON (`series_id`)

**约束**：仓储层只暴露 `append()`，禁止 UPDATE / DELETE。撤销不写日记。

#### `food_items` — 食物库

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | |
| `name` | TEXT NOT NULL | |
| `category` | TEXT | `grain` / `protein` / `vegetable` 等 |
| `serving_size` | REAL NOT NULL | 一份的量 |
| `serving_unit` | TEXT NOT NULL | `g` / `ml` / `个` |
| `calories` | REAL NOT NULL | kcal per 一份 |
| `protein_g` / `carb_g` / `fat_g` / `fiber_g` | REAL NOT NULL DEFAULT 0 | |
| `gi_value` | INTEGER | 升糖指数 |
| `notes` | TEXT | 维生素/矿物质手动标注 |
| `is_active` | BOOLEAN NOT NULL DEFAULT 1 | |
| `deleted_at` | TIMESTAMP | |
| `created_at` | TIMESTAMP NOT NULL | |

#### `meal_templates` + `meal_template_items` — 饮食模板

```
meal_templates
├── id           INTEGER PK
├── name         TEXT NOT NULL
├── day_type     TEXT NOT NULL          -- 'work'|'training'|'rest'|'compound'
├── description  TEXT
├── is_active    BOOLEAN NOT NULL DEFAULT 1
├── deleted_at   TIMESTAMP
└── created_at   TIMESTAMP NOT NULL

meal_template_items
├── id            INTEGER PK
├── template_id   FK → meal_templates ON DELETE CASCADE
├── meal_slot     TEXT NOT NULL  -- 'breakfast'|'lunch'|'dinner'|'snack'|'pre_workout'|'post_workout'
├── food_id       FK → food_items
├── quantity      REAL NOT NULL
└── sort_order    INTEGER NOT NULL DEFAULT 0
```

#### `daily_meal_plans` + `daily_meal_items` — 每日饮食

```
daily_meal_plans
├── id            INTEGER PK
├── date          DATE UNIQUE NOT NULL
├── day_type      TEXT NOT NULL           -- 自动推断，可手动覆盖
├── source        TEXT NOT NULL           -- 'auto_from_template'|'manual'|'edited'
├── template_id   FK → meal_templates  (可空)
├── notes         TEXT
└── created_at / updated_at

daily_meal_items
├── id            INTEGER PK
├── plan_id       FK → daily_meal_plans ON DELETE CASCADE
├── meal_slot     TEXT NOT NULL
├── food_id       FK → food_items
├── quantity      REAL NOT NULL
├── is_consumed   BOOLEAN NOT NULL DEFAULT 0
├── consumed_at   TIMESTAMP
├── notes         TEXT
└── sort_order    INTEGER NOT NULL DEFAULT 0
```

### 4.4 关键算法

#### 4.4.1 周期任务展开（日历渲染）

```python
def expand_calendar(start: date, end: date) -> dict[date, list]:
    result = defaultdict(list)

    # 一次性事件
    for ev in events.filter(deleted_at=None,
                             start_at__date__range=(start, end)):
        result[ev.start_at.date()].append({'type': 'event', ...})

    # 周期任务：仅取当前生效的规则版本
    rules = recurrence_rules.filter(
        is_active=True, deleted_at=None,
        dtstart__lte=end,
    ).filter(Q(dtend__isnull=True) | Q(dtend__gte=start))

    for rule in rules:
        window_start = max(rule.dtstart, start)
        window_end   = min(rule.dtend or end, end)
        for occ in rrule_parse(rule.rrule).between(window_start, window_end):
            inst = task_instances.get_or_none(rule_id=rule.id,
                                              occurrence_date=occ)
            result[occ].append({
                'type': 'task',
                'rule_id': rule.id,
                'series_id': rule.series_id,
                'title': (inst.override_title if inst else None) or rule.title,
                'status': derive_status(inst),  # pending|completed|withdrawn
            })

    return result
```

#### 4.4.2 规则修改（区分外观 / 排期）

```python
SCHEDULE_AFFECTING = {'rrule', 'time_of_day', 'duration_minutes', 'category'}

def modify_rule(rule_id, new_fields, effective_date=None):
    affects_schedule = bool(SCHEDULE_AFFECTING & new_fields.keys())

    if affects_schedule:
        assert effective_date is not None and effective_date > today()
        old = get(rule_id)
        old.dtend = effective_date - timedelta(days=1)
        old.save()
        new = old.clone(
            id=None,
            dtstart=effective_date,
            dtend=None,
            **new_fields,
        )
        new.save()  # series_id 继承自 old
    else:
        # 外观字段（title/description/tag_id）：原地更新
        old = get(rule_id)
        for k, v in new_fields.items():
            setattr(old, k, v)
        old.save()
```

#### 4.4.3 软删除规则

```python
def delete_rule(rule_id):
    rule = get(rule_id)
    rule.deleted_at = now()
    if rule.dtend is None or rule.dtend > today():
        rule.dtend = today()  # 历史保留，未来不再展开
    rule.save()
```

#### 4.4.4 打卡 / 撤销

```python
def checkin(rule_id, occurrence_date):
    inst = task_instances.get_or_create(
        rule_id=rule_id, occurrence_date=occurrence_date,
    )
    assert inst.completed_at is None        # 一次性
    assert inst.undone_at is None           # 撤销过则永久无法重打
    inst.completed_at = now()
    inst.save()

    rule = get_rule(rule_id)
    task_completion_log.append(
        rule_id=rule_id, series_id=rule.series_id,
        occurrence_date=occurrence_date,
        completed_at=inst.completed_at,
        title_snapshot=rule.title,
        tag_color_snapshot=rule.tag.color if rule.tag else None,
        category_snapshot=rule.category,
        notes=inst.notes,
    )

def undo(rule_id, occurrence_date):
    inst = task_instances.get(rule_id=rule_id, occurrence_date=occurrence_date)
    assert inst.completed_at is not None
    assert inst.undone_at is None           # 一次性，终态
    inst.undone_at = now()
    inst.save()
    # 日记不写撤销事件
```

#### 4.4.5 当日 day_type 推断

```python
def infer_day_type(d: date) -> str:
    tasks = tasks_on(d)  # 含 events + 展开后的 task_instances
    has_ex = any(t.category == 'exercise' for t in tasks)
    has_wk = any(t.category == 'work'     for t in tasks)
    if has_ex and has_wk: return 'compound'
    if has_ex:            return 'training'
    if has_wk:            return 'work'
    return 'rest'
```

复合日的预警逻辑（"精力不足""能量不足"）属于后续细节，不影响 schema。

### 4.5 应用层约束清单

SQLite 不支持完整的 CHECK / TRIGGER 表达，以下规则**由应用层保证**：

- 软删除：所有查询带 `deleted_at IS NULL` 过滤
- 撤销/打卡字段一次性：仓储 update 时校验目标字段未被修改
- `task_completion_log` 只追加：仓储不暴露 update / delete 方法
- 规则修改：`effective_date > today()` 强校验
- 规则改名：仅在不影响排期字段时允许原地更新；否则要求传 `effective_date`
- 标签删除：禁止删除仍被引用的标签（FK RESTRICT 已经强制）

迁移到 PostgreSQL 时，部分约束可下沉为 CHECK / 触发器。

## 5. 关键设计决策记录

| 决策 | 选择 | 替代方案 | 理由 |
|---|---|---|---|
| 后端语言 | Python (FastAPI) | Node (Hono/Fastify) | 未来接 LLM 做饮食推荐，Python 生态占优 |
| 数据库 | SQLite → PostgreSQL | MySQL；纯前端 IndexedDB | SQLite 单用户够用，PostgreSQL 公网部署时迁移 |
| Web 服务器 | Caddy | nginx | 配置短、自动 HTTPS |
| 远程访问 | Tailscale | frp / 公网 VPS | 零配置、端到端加密、单人免费 |
| 周期任务模型 | RRULE + 例外表 | 预生成全量实例 | 修改不需要批量改记录 |
| 任务身份 | `series_id` UUID 跨规则版本共享 | 直接用 rule_id 表示身份 | 规则改了多次仍是"同一任务"，支持成长追溯 |
| 规则修改语义 | 外观改原地、排期改切版本 | 永远切版本 / 永远原地 | 平衡"过去不变"与"易用性" |
| 修改生效日 | `effective_date > today` 强约束 | 允许任意日期 | 防止过去被改写 |
| 撤销语义 | 终态，写一次后不可逆 | 允许多次切换 | 字段不被频繁修改，状态稳定，对应应用层二次确认 |
| 历史命名 | 写时快照（Option A） | 实时 JOIN / 全局刷新 | "过去不变"的最朴素实现 |
| 删除 | 软删除（`deleted_at`） | 硬删除 / 归档表 | 历史可见、误操作可恢复 |
| 日历同步 | 自建为主，预留 .ics 导出 | 双向同步 Google/Apple | 双向同步复杂度爆炸，单人价值不足 |
| 饮食推荐 | 规则模板起步，LLM 后置 | 直接 LLM | 先稳定数据模型，LLM 作为增强层 |
| `day_type` | work/training/rest + compound | 三选一 | 高强度日双重任务很普遍，需独立分类 |
| 时区 | 全部存 UTC，前端转换 | 存本地时间 | 跨设备/跨时区一致性 |
| 食物数据来源 | 用户手录入 | 导入开源数据集 | 起步快，避免无用条目干扰搜索 |
| 标签关联 | 事件多标签，周期任务单标签 + category | 两者皆多标签 | 周期任务靠 category 已足够分类 |

## 6. 非功能性需求

- **响应式**：桌面 + 手机竖屏均需可用
- **离线容忍**：短暂断网时前端基础查看不应崩溃（缓存当日数据）
- **数据安全**：SQLite 文件需要定期备份机制（最简：cron + 复制到另一磁盘/网盘）
- **可观测**：后端结构化日志即可，不上 APM
- **性能**：单用户场景无压力，不做特殊优化

## 7. 不在范围内（明确不做）

- 移动 app / 小程序
- 用户注册 / 登录系统（当前阶段）
- 公网部署 / 域名 / HTTPS 证书（当前阶段）
- 与第三方日历（Google / Apple / Outlook）双向同步
- 社交分享 / 多用户协作
- 复杂的营养学计算（如精确到氨基酸谱），先做宏观营养素

## 8. 部署阶段路线

**阶段 A — 自用**（当前目标）
- Docker Compose 单机部署
- SQLite 文件存储
- Tailscale 远程访问
- HTTP 内网访问，无证书

**阶段 B — 朋友试用**（条件触发）
- 迁移 PostgreSQL
- 加用户表 + 简单认证（JWT 或 session）
- 上 VPS + 域名 + Caddy 自动 HTTPS
- docker-compose 文件复用，仅改环境变量

## 9. 待定 / 开放问题

数据模型已 v1 锁定。剩余开放项：

- [ ] UI 库：Element Plus vs Naive UI（开发界面时选定）
- [ ] 日历组件：FullCalendar vs vue-cal（移动端体验对比后定）
- [ ] 复合日（compound）的餐单设计粒度
- [ ] SQLite 文件备份策略具体方案
- [ ] 复合日的预警阈值 / 提示语设计

## 10. 给 AI agent 的工作约定

- 任何 schema 变更必须通过 Alembic migration，禁止手改数据库
- 修改本文档第 4 节（数据模型）需要在第 5 节追加决策记录
- 新增功能优先评估是否能复用现有表，避免表爆炸
- 前端组件保持小而专一，状态尽量收敛到 Pinia store
- 提交前确保 `docker compose up` 在干净环境可启动
- 不引入未在本文档列出的核心依赖；如必须，先更新本文档的「技术栈」章节
- 软删除、一次性字段、append-only 日志等约束必须在仓储层强制，禁止在业务代码各处散落判断
