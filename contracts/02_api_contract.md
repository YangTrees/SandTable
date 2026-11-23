# 心理沙盘发展性评估 · 前后端 API 契约

本文件描述 `backend/app/main.py` 与 `backend/app/admin_api.py` 的**当前实现**，不是规划稿。
默认服务地址 `http://127.0.0.1:8000`；页面路由与接口同源部署。
数据库结构见 `contracts/01_database_schema.sql`。

---

## 1. 通用约定

### 1.1 响应包络

所有 JSON 接口统一返回：

```json
{
  "code": "OK",
  "message": "success",
  "data": {},
  "trace_id": "req_xxx"
}
```

- 成功判定：HTTP 2xx 且 `body.code === "OK"`；业务数据在 `body.data`。
- 失败时 `code` 为具体错误码，`message` 为可展示文案，`data` 可含 `field_errors`。
- `trace_id` 优先取请求头 `X-Request-Id`，否则服务端生成。

### 1.2 鉴权

当前为**账号会话 + 角色分权**模型：

- 教职员工通过 `POST /api/v1/admin/login` 登录，学生通过 `POST /api/v1/workbench/login` 登录；成功后返回会话 token。
- 后续请求使用 `Authorization: Bearer <token>`；会话默认 12 小时，可在 `.env` 配置。
- `/api/v1/admin/*` 拒绝学生账号；`/api/v1/workbench/*` 只接受学生账号。
- 个体报告、审核、修订、分享、撤回接口只允许 `counselor` 与 `super_admin`；`teacher` 只能访问班级汇总，服务端会移除个体风险字段。
- `X-Counselor-Token` 仅作为受控运维脚本的兼容入口，必须同时设置 `ENABLE_SERVICE_TOKEN=true` 和强随机 `COUNSELOR_TOKEN` 才生效；默认关闭且没有内置默认值。
- 公开分享报告使用 `GET /api/v1/share/access`，在请求头 `X-Share-Token` 中携带分享令牌，不把令牌放进 JSON 接口路径。


### 1.3 通用错误码

| HTTP | code | 场景 |
| --- | --- | --- |
| 401 | `HTTP_ERROR` | 令牌缺失或错误 |
| 404 | `NOT_FOUND` / `HTTP_ERROR` | 记录不存在 |
| 409 | `MODEL_NOT_CONFIGURED` / 账号冲突 | 模型未配置、账号重复等 |
| 422 | `VALIDATION_INVALID_PAYLOAD` | Pydantic 校验失败，`data.field_errors` 给出字段 |
| 502 | `REPORT_GENERATION_FAILED` / `MODEL_CALL_FAILED` | 报告生成或模型调用失败 |

### 1.4 页面路由

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 入口页 |
| GET | `/workbench` | 沙盘工作台（`sandplay_workbench_react.html`） |
| GET | `/report-viewer` | 报告查看页（`report_viewer_v2.html`） |
| GET | `/admin` | 管理后台（`admin_dashboard.html`） |
| GET | `/share/{token}` | 兼容旧分享链接，303 跳转到 fragment 形式 |
| GET | `/media/{assessment_id}/{filename}` | 沙盘图 / 成绩单，必须带短期签名 `?exp=&sig=` |
| GET | `/docs` | 仅 `ENABLE_API_DOCS=true` 时开放 |

---

## 2. 工作台与报告

### 2.1 健康检查

`GET /api/v1/health`

```json
{ "status": "ok", "time": "2026-11-22T03:00:00Z" }
```

### 2.2 创建评估并生成报告

`POST /api/v1/assessments`

`multipart/form-data`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `payload` | string(JSON) | 是 | 工作台导出的完整 JSON |
| `sandplay_image` | file | 否 | 沙盘俯视截图；也可改用 `sandplay_image_base64` |
| `sandplay_image_base64` | string | 否 | data URL 或纯 base64 |
| `transcript_image` | file | 否 | 转录图；也可改用 `transcript_image_base64` |
| `transcript_image_base64` | string | 否 | 同上 |

`payload` 核心结构：

```json
{
  "schema_version": "1.1",
  "student": {
    "student_no": "PS-2026-018",
    "name": "顾南",
    "grade_level": "初一",
    "gender": "男",
    "school_name": "中科青行实验学校",
    "class_name": "初一 1 班",
    "seat_no": "3排2座",
    "contact_phone": "138****0000",
    "academic_scores": {
      "exam_name": "期中考试",
      "exam_date": "2026-11-10",
      "total_score": 286,
      "class_rank": "12/45",
      "subjects": { "语文": 92, "数学": 88, "英语": 90, "科学": 86, "综合": 84 }
    }
  },
  "representative_item_id": "item-001",
  "representative_item_name": "灯塔",
  "representative_category": "建筑与庇护",
  "self_image": "一盏灯",
  "self_image_note": "希望自己也能照亮别人",
  "items": [
    {
      "id": "item-001",
      "label": "灯塔",
      "category": "建筑与庇护",
      "grid_key": "center",
      "position": { "x": 0.12, "z": -0.08 },
      "scale": 1,
      "rotation": 0,
      "mirrored": false
    }
  ],
  "grid_distribution": {
    "cells": [{ "key": "center", "count": 1 }],
    "coverage": { "occupied_ratio": 0.18, "blank_ratio": 0.82 },
    "summary": "中心聚集"
  },
  "heightmap": { "width": 1200, "depth": 900, "cols": 161, "rows": 101, "values": [], "stats": {} },
  "terrain_metrics": { "mountains": 2, "rivers": 1, "flatten_ops": 4, "brush": "smooth" },
  "process_telemetry": {
    "duration_sec": 412,
    "brush_strokes": 18,
    "terrain_ops": 6,
    "undo_count": 2,
    "redo_count": 1,
    "mirror_count": 0,
    "snapshot_count": 3
  },
  "spatial_relations": { "clusters": [], "isolated_items": [], "barriers": [] },
  "process_snapshots": [
    { "index": 1, "elapsed_sec": 120, "image_base64": "data:image/jpeg;base64,...", "note": "" }
  ],
  "sandplay_description": "我把灯塔放在中间……",
  "self_narrative": "最近总觉得……",
  "sand_name": "海边的灯塔",
  "interaction_summary": {},
  "consent": true
}
```

校验规则：

- `payload` 必须是合法 JSON，且符合 `AssessmentPayload`。
- `sandplay_description` 至少 10 个字符，最多 4000 字。
- `consent` 必须为 `true`，否则返回 422 `CONSENT_REQUIRED`。
- 学生提交中的 `teacher_observation` 与 `_` 开头的内部字段会被服务端丢弃，避免伪造教师观察或污染报告。
- `sand_name` 为可选字段（给沙盘起名），随 `input_payload` 保存，不写入 `self_image`。
- `sandplay_image` / `transcript_image` 只接受可解码的 PNG / JPEG / WebP，单张不超过 24MB；服务端会重编码为 PNG 后再保存，拒绝伪造扩展名或超大像素图。
- `representative_item_id` 必须存在于 `items[].id`，否则 422 `VALIDATION_REPRESENTATIVE_NOT_FOUND`。
- `self_image` 为可选独立字段（最长 120 字），不要求存在于 `items[].id`；只进入第二章自我意象假设与第六章访谈，不直接参与风险分级。
- `self_image_note` 为可选补充说明（最长 800 字）。
- `heightmap.depth` 默认 `900`（4:3 沙箱）。
- `student.academic_scores.subjects` 非空时，服务端把它作为成绩依据传入报告提示词；报告第四章写入 `structured_scores`、`score_source="structured_entry"`，并注明“待与成绩单核对”。提供成绩单图片时 `score_source` 为 `mixed`。
- 成功返回 `assessment summary + report + sandplay_image_url + transcript_image_url`。

`data` 关键字段：

```json
{
  "assessment_id": "uuid",
  "status": "completed",
  "student_name": "顾南",
  "student_no": "PS-2026-018",
  "grade_level": "初一",
  "gender": "男",
  "school_name": "中科青行实验学校",
  "class_name": "初一 1 班",
  "representative_item_id": "item-001",
  "representative_item_name": "灯塔",
  "self_image": "一盏灯",
  "self_image_note": "希望自己也能照亮别人",
  "report_engine": "multimodal",
  "created_at": "2026-11-22T03:00:00Z",
  "counselor_report_url": "/api/v1/reports/{id}",
  "report": { "meta": {}, "chapter_1_overview": {}, "...": "..." },
  "sandplay_image_url": "http://127.0.0.1:8000/media/{id}/sandplay.png",
  "transcript_image_url": null,
  "counselor_access": { "header": "Authorization: Bearer <session-token>" },
  "share_hint": "POST /api/v1/reports/{id}/share"
}
```

报告固定九章，章节不可缺失：

`chapter_1_overview`、`chapter_2_imagery`、`chapter_3_six_dimensions`、`chapter_4_academic`、`chapter_5_risk`、`chapter_6_interview`、`chapter_7_career`、`chapter_8_training_modules`、`chapter_9_general_advice`。

服务端派生展示字段（不由模型直接生成）：

| 字段 | 说明 |
| --- | --- |
| `summary_card` | 顶部摘要卡：3–5 个核心信号、一句话、下一步；`summary_card.public` 为家长/学生脱敏版，不含风险分级 |
| `longitudinal_comparison` | 同一 `student_no` 上一份已完成报告的九维变化；`availability/comparability/risk_changes` 由服务端计算 |
| `chapter_2_imagery.self_image` | 自我像独立对象：假设 A/B、核验问题与“仅用于访谈、不参与风险分级”边界 |
| `chapter_1_overview.holistic_visual_check.visual_risk_objects` | 视觉高危物体：类型、位置、朝向、人物关系、场景语境、severity |

风险优先规则（服务端硬门控）：

- 单件非死亡类 `high_risk` 沙具 → `L3_ORANGE`，需人工复核场景语境。
- 死亡类符号（骷髅/墓碑/棺材/尸体/遗照/坟墓）、两件及以上 `high_risk`、明确的负向文本、掩埋/破坏过程 → `L4_RED`。
- 视觉高危物体单独筛查：单件枪械/刀具/血/伤/排泄物等 `high` 物体 → L3；尸体/悬吊/两件及以上 `high` 物体 → L4；军事/警察/博物馆/玩具陈列或厕所/医疗语境 → 最多 `watch`，不自动升级。

报告 `meta` 关键字段：

| 字段 | 说明 |
| --- | --- |
| `report_no` | 报告编号 |
| `engine` | `multimodal` 或 `demo` |
| `demo_report` | 是否 Demo 报告；`true` 时报告页与后台都显示 Demo 标识 |
| `review_edited` | 是否经过人工修订 |
| `review_revision` | 人工修订版本号 |
| `review_applied_at` | 审核通过合并时间 |
| `reviewer_id` | 修订人 |
| `reanalyzed_at` / `reanalyze_source` | 重新分析时间与来源 |

Demo 回退默认关闭（`ALLOW_DEMO_REPORT=false`）。模型失败时返回 502，不再静默生成模板报告。

### 2.3 读取评估与报告

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/assessments/{assessment_id}` | 评估摘要 + `report` |
| GET | `/api/v1/reports/{assessment_id}` | 报告全文 + 摘要 |
| POST | `/api/v1/reports/{assessment_id}/reanalyze` | 用多模态模型重新生成 |

重新分析规则：

- 未配置 `MULTIMODAL_API_KEY` 返回 409 `MODEL_NOT_CONFIGURED`。
- 原图缺失返回 409 `IMAGE_NOT_FOUND`。
- 只接受 `engine=multimodal` 的结果，失败保留原报告不覆盖。
- 成功后 `report_revision` 归零；`report_reviews` 重置为 `pending`，清空 `ai_report_json / draft_report_json / draft_note` 与时间戳，避免旧修订污染新报告。

### 2.4 分享

`POST /api/v1/reports/{assessment_id}/share`

```json
{ "expires_days": 30, "regenerate": false }
```

- 复用未过期、未撤销的分享链接；`regenerate=true` 强制换新 token。
- `expires_days` 范围 1–3650；省略时使用 `SHARE_DEFAULT_EXPIRES_DAYS`，默认 30 天。
- 返回 `share_token`、`share_url`（令牌位于 fragment）、`api_url`、二维码 base64 与过期时间。
- `share_url` 形如 `https://<域名>/report-viewer#share_token=<token>`，页面加载时不会把令牌发送给服务端。
- 分享报告的沙盘图 / 成绩单地址在序列化时重新签名为短期 URL，不能直接枚举 `/media`。


`GET /api/v1/share/access`

- 无需登录会话，但必须携带 `X-Share-Token: <token>`。
- 返回脱敏后的报告；风险章节、风险等级、咨询师字段和原始记录不回传。
- 链接过期或撤销返回 410/404。

`GET /share/{token}`：兼容旧二维码的跳转入口，会 303 跳到 fragment 形式；新分享链接不再使用该路径。

`DELETE /api/v1/shares/{token}`：撤销分享，需咨询师 / 超级管理员会话。

---

## 3. 管理后台

前缀 `/api/v1/admin`，除登录外均需 `Authorization: Bearer <session-token>`；个体报告相关接口仅 `counselor / super_admin` 可用。

### 3.1 初始化数据

`GET /bootstrap` → `system / roles / users / counts{users,reports,pending_reviews}`

`pending` 统计口径：无审核记录，或状态为 `pending` / `changes`。

### 3.2 用户

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/users?q=&role=` | 列表；`q` 匹配姓名、账号、部门、学号 |
| POST | `/users` | 新建 |
| PATCH | `/users/{user_id}` | 更新 |
| DELETE | `/users/{user_id}` | 删除 |

新建/更新字段：`name / account / role_key / department / grade_level / class_name / student_no / status`。

- `role_key` ∈ `counselor / teacher / student / parent`。
- `status` ∈ `active / disabled`。
- 账号重复返回 409。

### 3.3 报告列表与筛选

`GET /reports`

| 参数 | 说明 |
| --- | --- |
| `q` | 匹配学生姓名、学号、报告编号、代表沙具、学校、班级、座位 |
| `status` | `all / pending / changes / approved / rejected` |
| `school` | 学校全等匹配；空字符串表示不限 |
| `class_name` | 班级全等匹配 |
| `grade` | 年级全等匹配 |
| `date_from` / `date_to` | `YYYY-MM-DD`，按创建时间闭区间；非法日期忽略 |
| `limit` | 1–200，默认 100 |

返回：

```json
{
  "reports": [
    {
      "assessment_id": "uuid",
      "report_no": "PS-XXXXXXXX",
      "student_name": "顾南",
      "student_no": "PS-2026-018",
      "grade_level": "初一",
      "gender": "男",
      "school_name": "中科青行实验学校",
      "class_name": "初一 1 班",
      "seat_no": "3排2座",
      "contact_phone": "138****0000",
      "academic_scores": {},
      "representative_item_name": "灯塔",
      "created_at": "2026-11-22T03:00:00Z",
      "updated_at": "2026-11-22T03:00:00Z",
      "report_revision": 0,
      "generation_status": "completed",
      "engine": "multimodal",
      "demo_report": false,
      "risk_level": "L1",
      "review_status": "pending",
      "review_note": "",
      "has_review_draft": false,
      "share_count": 0,
      "chapter_count": 9
    }
  ],
  "total": 99,
  "filters": { "school": "", "class_name": "", "grade": "", "date_from": "", "date_to": "" },
  "facets": { "schools": ["未填写"], "classes": ["未填写"], "grades": ["初一"] }
}
```

- `facets` 由**学校/班级/年级/日期筛选后**的报告集合计算，不受 `status` 与 `q` 影响。
- `total` 为 `limit` 截断前的条数。

### 3.4 统计

`GET /stats?school=&class_name=&grade=&date_from=&date_to=`

返回：

```json
{
  "summary": {
    "total_reports": 99,
    "pending_reviews": 0,
    "approved_reports": 0,
    "high_risk_reports": 36,
    "share_links": 2,
    "total_items": 1234,
    "sample_sufficient": true
  },
  "risk_distribution": [{ "level": "L1", "label": "L1 平稳", "value": 63 }],
  "high_risk_students": [],
  "top_items": [{ "name": "灯塔", "value": 12 }],
  "item_categories": [{ "name": "建筑与庇护", "value": 40 }],
  "grid_heatmap": [{ "label": "左上", "value": 3 }],
  "module_distribution": [],
  "grade_distribution": [{ "name": "初一", "value": 10 }],
  "class_distribution": [{ "name": "初一 1 班", "value": 10 }],
  "school_distribution": [{ "name": "中科青行实验学校", "value": 10 }],
  "scope": {
    "school": "", "class_name": "", "grade": "",
    "date_from": "", "date_to": "",
    "total_reports": 99
  }
}
```

### 3.5 审核上下文

`GET /reports/{assessment_id}/review-context`

```json
{
  "assessment_id": "uuid",
  "report_revision": 1,
  "review": {
    "status": "changes",
    "note": "",
    "reviewer_id": "counselor-01",
    "draft_note": "第二章假设改写",
    "has_draft": true,
    "draft_updated_at": "2026-11-22T03:10:00Z",
    "review_applied_at": null,
    "updated_at": "2026-11-22T03:10:00Z"
  },
  "editable_sections": [
    { "key": "chapter_2_imagery", "label": "第二章 · 探索性假设与核验问题" },
    { "key": "chapter_6_interview", "label": "第六章 · 访谈问题" },
    { "key": "chapter_9_general_advice", "label": "第九章 · 总体建议" }
  ],
  "ai_report": {},
  "effective_report": {},
  "draft_sections": {},
  "preview_report": {}
}
```

- `ai_report`：首次审核时落库的 AI 原稿；人工修订不覆盖它。
- `effective_report`：当前对外报告（可能是已合并修订的版本）。
- `preview_report`：AI 原稿 + 草稿的预览。
- 可编辑范围固定为三章：`chapter_2_imagery / chapter_6_interview / chapter_9_general_advice`；`chapter_5_risk` 等风险章节不允许草稿覆盖。

### 3.6 保存审核草稿

`PUT /reports/{assessment_id}/review-draft`

```json
{
  "reviewer_id": "counselor-01",
  "note": "调整第二章假设，补充访谈问题",
  "draft": {
    "chapter_2_imagery": {},
    "chapter_6_interview": {},
    "chapter_9_general_advice": {}
  }
}
```

规则：

- `draft`（或 `report`）至少包含一个可编辑章节，否则 422。
- 首次保存会把当时的 `report_json` 写入 `ai_report_json`。
- 状态自动从 `pending` / `approved` 变为 `changes`；`rejected` 保持不变。
- 只保存草稿，不改变对外报告；`report_revision` 不变。

### 3.7 提交审核

`POST /reports/{assessment_id}/review`

```json
{
  "status": "approved",
  "note": "已核对，同意发布",
  "reviewer_id": "counselor-01",
  "draft": { "chapter_2_imagery": {} }
}
```

- `status` ∈ `pending / changes / approved / rejected`，其他值 422。
- `rejected` 仅记录状态与备注，不合并草稿。
- `approved` 且存在草稿：把三章草稿合并进当前报告，`report_revision + 1`，写 `meta.review_edited / review_edited_sections / review_revision / review_applied_at / reviewer_id`，清空 `draft_report_json`。
- 返回 `report_revision` 与最新 `review` 对象。

---

## 4. 报告阅读页约定

`report_viewer_v2.html` 通过 `GET /api/v1/reports/{id}` 拉取咨询师报告，并通过 `GET /api/v1/share/access` + `X-Share-Token` 支持公开只读视图。咨询师报告页从管理后台打开，复用后台 `sessionStorage` 会话；不再支持 URL 查询参数或 `localStorage` 中的服务令牌。

- 当 `report.meta.demo_report === true` 或 `engine === "demo"` 时，页面顶部展示 Demo 标识，提示“演示报告，非真实评估结论”。
- Demo 标识在报告页、管理后台列表、后台详情三处一致。
- 分享视图隐藏联系方式、学号、座位与家庭背景等敏感字段。

---

## 5. 明确不再提供的接口

以下旧契约内容已废弃，当前实现中不存在：

- `POST /api/v1/auth/login`、JWT / Bearer 登录换票。
- `GET/POST /api/v1/sessions` 会话管理。
- `GET/POST /api/v1/analysis-jobs` 异步分析任务。
- 归一化 `0–1` 坐标契约；当前 `items[].position` 为沙盘局部坐标，`heightmap` 使用 `1200×900` 网格。
- 多表拆分的 `report_revisions` 历史版本表；修订版本仅由 `assessments.report_revision` 与 `report_reviews` 记录。

前端字段名以工作台导出为准，不在契约层强行改名为理论模块命名。
