# 心理沙盘学习动力发展性评估系统 API 契约

版本：`v1.0`  
协议：REST + JSON  
Base URL：`/api/v1`  
数据库契约：`contracts/01_database_schema.sql`  
适用端：React 沙盘端、Admin Dashboard、咨询师审核端、学生/家长分享端、AI 评估引擎、数据统计端

> 本文件只定义接口契约，不包含业务实现代码。后续前后端、AI 引擎和报表模块必须严格对齐本契约。

---

## 1. 通用约定

### 1.1 请求与认证

- 除公开分享接口外，所有接口均要求：

```http
Authorization: Bearer <access_token>
Content-Type: application/json; charset=utf-8
X-Request-Id: <client-generated-request-id>
```

- 文件上传使用：

```http
Content-Type: multipart/form-data
```

- 创建类接口建议携带：

```http
Idempotency-Key: <uuid>
```

- 所有 ID 均为 UUID 字符串。
- 所有时间均为 UTC ISO8601，例如：`2026-11-19T10:30:00Z`。
- 坐标采用归一化坐标：`x`、`y` 均为 `0 ~ 1`，以沙盘左上角为原点。
- 旋转角度单位为度，范围：`0 <= rotation < 360`。
- 面积占比、留白率、得分率均为 `0 ~ 1` 小数。

### 1.2 统一响应包裹

成功：

```json
{
  "code": "OK",
  "message": "success",
  "data": {},
  "trace_id": "req_01J..."
}
```

失败：

```json
{
  "code": "VALIDATION_INVALID_PAYLOAD",
  "message": "nine_grid_distribution 必须包含 9 个区域",
  "data": {
    "field_errors": [
      {
        "field": "nine_grid_distribution",
        "reason": "expected 9 cells"
      }
    ]
  },
  "trace_id": "req_01J..."
}
```

### 1.3 分页响应

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "page": 1,
    "page_size": 20,
    "total": 135,
    "items": []
  },
  "trace_id": "req_01J..."
}
```

统一查询参数：

| 参数 | 类型 | 默认值 | 说明 |
|---|---:|---:|---|
| `page` | integer | 1 | 页码，从 1 开始 |
| `page_size` | integer | 20 | 每页条数，最大 100 |
| `keyword` | string | - | 模糊搜索 |
| `sort_by` | string | created_at | 排序字段 |
| `sort_order` | string | desc | `asc` / `desc` |

### 1.4 异步任务响应

创建异步 AI 分析、OCR 或导出任务时返回：

```http
HTTP/1.1 202 Accepted
```

```json
{
  "code": "ACCEPTED",
  "message": "job accepted",
  "data": {
    "job_id": "uuid",
    "status": "queued",
    "poll_url": "/api/v1/analysis-jobs/uuid"
  },
  "trace_id": "req_01J..."
}
```

---

## 2. 角色与权限矩阵

| 能力 | super_admin | org_admin | counselor | teacher | student | guardian | public_token |
|---|---:|---:|---:|---:|---:|---:|---:|
| 管理组织、班级、用户 | 是 | 本机构 | 否 | 否 | 否 | 否 | 否 |
| 管理沙具资产 | 是 | 本机构 | 建议只读 | 只读 | 只读 | 否 | 否 |
| 创建沙盘会话 | 是 | 是 | 是 | 可代建 | 本人 | 否 | 否 |
| 提交过程事件/最终沙盘 | 是 | 是 | 是 | 可协助 | 本人 | 否 | 否 |
| 上传自述/成绩单 | 是 | 是 | 是 | 可协助 | 本人 | 可补充 | 否 |
| 发起 AI 分析 | 是 | 是 | 是 | 否 | 否 | 否 | 否 |
| 查看完整报告 | 是 | 本机构 | 是 | 按授权 | 脱敏版 | 脱敏版 | 脱敏版 |
| 查看九维风险研判 | 是 | 本机构管理员可配置 | 是 | 默认否 | 否 | 否 | 否 |
| 审核/发布报告 | 是 | 可配置 | 是 | 否 | 否 | 否 | 否 |
| 查看统计数据 | 是 | 本机构 | 是 | 汇总可见 | 否 | 否 | 否 |

### 2.1 风险内容隔离红线

以下字段/接口响应在学生、家长、公开分享端必须剔除：

- `risk_assessment`
- `risk_assessments`
- `counselor_note`
- `review_note`
- `ai_raw_prompt`
- `ai_raw_response`
- `ai_analysis_inputs`
- `ai_analysis_outputs`

公开分享接口只允许返回：

- `overview`
- `imagery_analysis`
- `six_dimensions`
- `academic_evaluation`
- `interview_suggestions` 中适合家庭查看的部分
- `career_strengths`
- `training_modules`
- `general_advice`
- `disclaimer`

---

## 3. 核心枚举字典

### 3.1 用户角色 `user_role`

```text
super_admin | org_admin | counselor | teacher | student | guardian
```

### 3.2 沙盘会话状态 `session_status`

```text
draft -> collecting -> submitted -> analyzing -> analyzed -> report_review -> published -> archived
                              \-> failed
```

### 3.3 成绩单 OCR 状态 `ocr_status`

```text
uploaded -> processing -> parsed -> confirmed
                 \-> failed -> processing
```

### 3.4 AI 任务状态 `analysis_job_status`

```text
queued -> running -> succeeded
                \-> failed -> retrying -> running
                \-> cancelled
```

### 3.5 报告状态 `report_status`

```text
draft -> reviewing -> approved -> published -> archived
           ^          |
           |---------- rejected
```

### 3.6 风险等级 `risk_level`

```text
L1 平稳 | L2 轻度关注 | L3 中度预警 | L4 高度预警
```

### 3.7 九宫格编码 `grid_cell_code`

```text
top_left | top_center | top_right
middle_left | center | middle_right
bottom_left | bottom_center | bottom_right
```

### 3.8 八大沙具分类 `asset_category_code`

```text
person_role
building_home
nature_plant
animal_myth
vehicle_tool
study_life
mystic_symbol
food_abundance
```

### 3.9 六维评估编码 `evaluation_dimension_code`

```text
cognitive_diagnosis
subject_selection
interest_potential
academic_planning
family_ecology
motivation_rebuild
```

### 3.10 九维风险编码 `risk_dimension_code`

```text
depression
anxiety
academic_stress
learning_burnout
obsession
paranoia
hostility
interpersonal_sensitivity
self_harm_risk
```

### 3.11 六大训练模块编码 `training_module_code`

```text
focus_flow
logic_expression
spatial_transfer
interpersonal_emotion
goal_planning
family_collaboration
```

---

## 4. 核心 JSON Schema

## 4.1 沙盘最终状态 `SandplayFinalStatePayload`

用于：

```http
PUT /api/v1/sessions/{sessionId}/final-state
```

请求示例：

```json
{
  "schema_version": "1.0",
  "sandbox_snapshot_file_id": "uuid",
  "process_metrics": {
    "duration_seconds": 65,
    "raise_sand_count": 4,
    "dig_sand_count": 2,
    "dig_water_count": 1,
    "smooth_sand_count": 1,
    "place_count": 21,
    "move_count": 5,
    "scale_count": 3,
    "rotate_count": 4,
    "remove_count": 2,
    "undo_count": 1,
    "redo_count": 0,
    "clear_count": 0,
    "hesitation_ms_total": 8300
  },
  "terrain_metrics": {
    "heightmap_file_id": "uuid",
    "raised_area_ratio": 0.12,
    "water_area_ratio": 0.08,
    "blank_ratio": 0.37
  },
  "nine_grid_distribution": [
    {
      "grid_cell_code": "top_left",
      "item_count": 4,
      "area_ratio": 0.13,
      "blank_ratio": 0.62,
      "dominant_categories": ["person_role", "nature_plant"]
    }
  ],
  "miniatures_list": [
    {
      "miniature_id": "uuid",
      "code": "person_soldier_001",
      "name": "军人",
      "category": "person_role",
      "x": 0.72,
      "y": 0.38,
      "z": 0,
      "scale": 1.2,
      "rotation": 45,
      "flipped": false,
      "grid_cell_code": "middle_right",
      "cluster_id": "cluster_01",
      "is_enclosed": true,
      "is_final": true,
      "metadata": {
        "nearby_miniature_codes": ["building_fence_001", "building_watchtower_001"]
      }
    }
  ],
  "self_report": {
    "content": "我最近不太想去学校，想待在自己搭的地方。",
    "mood_tags": ["焦虑", "退缩"]
  },
  "transcript_id": "uuid",
  "client_meta": {
    "device": "desktop",
    "browser": "Chrome",
    "viewport": "1920x1080",
    "canvas_width": 1600,
    "canvas_height": 1200,
    "view_mode": "top",
    "theme": "warm_morandi"
  }
}
```

校验规则：

- `nine_grid_distribution` 必须且只能包含 9 个格子。
- `miniatures_list[*].grid_cell_code` 必须属于九宫格编码。
- `x`、`y` 必须在 `0 ~ 1`。
- `scale > 0`。
- `sandbox_snapshot_file_id` 必须指向 `visibility != public` 的沙盘最终截图。
- 提交前必须存在有效 `consent_records.status = signed`。

## 4.2 过程事件批量上报 `ProcessEventBatchPayload`

用于：

```http
POST /api/v1/sessions/{sessionId}/events:batch
```

```json
{
  "schema_version": "1.0",
  "events": [
    {
      "seq_no": 1,
      "event_type": "place",
      "tool_type": "miniature_palette",
      "target_item_id": null,
      "client_ts": "2026-11-19T10:31:00Z",
      "payload": {
        "miniature_code": "person_soldier_001",
        "x": 0.72,
        "y": 0.38,
        "scale": 1.2,
        "rotation": 45
      }
    },
    {
      "seq_no": 2,
      "event_type": "dig_water",
      "tool_type": "water_brush_medium",
      "target_item_id": null,
      "client_ts": "2026-11-19T10:31:18Z",
      "payload": {
        "brush_size": "medium",
        "strength": 0.8,
        "area_ratio_delta": 0.03
      }
    }
  ]
}
```

服务端责任：

- 按 `session_id + seq_no` 幂等写入。
- 重复批次不得重复追加。
- `seq_no` 必须连续；如允许断点续传，可在响应中返回 `next_expected_seq_no`。

## 4.3 AI 分析请求 `AnalysisJobCreatePayload`

```json
{
  "prompt_template_code": "sandplay_assessment",
  "prompt_template_version": "v1.0",
  "model_name": "multimodal-llm-default",
  "options": {
    "include_process_events": true,
    "include_theory_context": true,
    "strict_schema": true,
    "temperature": 0.2
  }
}
```

AI 引擎输入由服务端组装，前端不得直接提交完整 Prompt。

## 4.4 报告输出 `AssessmentReportOutput`

固定顶层字段：

```json
{
  "overview": {},
  "imagery_analysis": [],
  "six_dimensions": [],
  "academic_evaluation": {},
  "risk_assessment": [],
  "interview_suggestions": [],
  "career_strengths": [],
  "training_modules": [],
  "general_advice": {}
}
```

### 4.4.1 `overview`

```json
{
  "cluster_area": "沙具主要聚集在中部，呈边界化布局。",
  "blank_area": "外围存在较大留白，提示外部互动意愿需进一步访谈确认。",
  "category_stats": [
    {"category": "person_role", "count": 8, "ratio": 0.38}
  ],
  "scene_imagery": "整体呈防御型院落场景，基调偏谨慎。",
  "nine_grid_analysis": [
    {
      "grid_cell_code": "center",
      "item_count": 9,
      "interpretation": "中心区域承载较多安全空间建设线索。"
    }
  ]
}
```

### 4.4.2 `imagery_analysis[]`

```json
{
  "theme": "安全感诉求与边界防御",
  "symbolic_miniatures": ["栅栏", "岗哨", "军人"],
  "hypothesis": "受测者可能通过构建清晰边界来获得可控感，该假设需结合访谈确认。",
  "theory_concept_codes": ["boundary_defense", "free_protected_space"]
}
```

### 4.4.3 `six_dimensions[]`

固定 6 项：

```json
{
  "dimension_code": "cognitive_diagnosis",
  "dimension_name": "全学科认知诊断",
  "confidence": "high",
  "conclusion": "理解记忆类能力较突出，逻辑应用类能力可继续支持。",
  "theory": "布鲁姆认知目标分类学、认知负荷理论",
  "evidence": ["文科得分率较高", "理科应用题完成度偏低", "沙盘布局有明确区域划分"],
  "abilities_to_improve": ["理科逻辑推理", "结构化解题表达"],
  "target_module_codes": ["logic_expression", "spatial_transfer"]
}
```

### 4.4.4 `risk_assessment[]`

固定 9 项，仅咨询师可见：

```json
{
  "dimension_code": "anxiety",
  "dimension_name": "焦虑",
  "level": "L2",
  "conclusion": "存在与学业压力相关的焦虑线索，建议访谈确认。",
  "evidence": ["自述近期紧张", "沙盘边界化布局", "近期成绩波动"],
  "norm_note": "本次无量表数据，为观察性判断，建议补测。",
  "counselor_only": true
}
```

### 4.4.5 `training_modules[]`

```json
{
  "module_code": "focus_flow",
  "module_name": "模块一：专注力与沉浸训练（心流模块）",
  "reason": "帮助在低压任务中逐步恢复胜任感。",
  "actions": {
    "teacher": ["设置 20 分钟单任务时段"],
    "guardian": ["执行 25 分钟专注 + 5 分钟休息"],
    "student": ["每天完成 1 轮限时训练并记录走神次数"]
  }
}
```

---

## 5. 文件上传与下载

### 5.1 上传文件

```http
POST /api/v1/files
```

权限：登录用户；公开端不可用。  
请求：`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `file` | binary | 是 | 文件内容 |
| `purpose` | string | 是 | `snapshot`、`heightmap`、`transcript`、`avatar`、`asset`、`export`、`attachment` |
| `visibility` | string | 否 | `private`、`organization`、`counselor_only` |

响应：

```json
{
  "file_id": "uuid",
  "file_name": "snapshot.png",
  "mime_type": "image/png",
  "size_bytes": 1024000,
  "sha256": "hex",
  "purpose": "snapshot",
  "visibility": "private"
}
```

### 5.2 获取短期下载地址

```http
GET /api/v1/files/{fileId}/download-url
```

响应：

```json
{
  "file_id": "uuid",
  "download_url": "https://storage.example.com/signed-url",
  "expires_in_seconds": 300
}
```

---

## 6. 认证接口

### 6.1 登录

```http
POST /api/v1/auth/login
```

请求：

```json
{
  "username": "counselor01",
  "password": "plain-password",
  "organization_code": "school-001"
}
```

响应：

```json
{
  "access_token": "jwt",
  "refresh_token": "jwt",
  "token_type": "Bearer",
  "expires_in_seconds": 7200,
  "user": {
    "id": "uuid",
    "display_name": "咨询师",
    "role": "counselor",
    "organization_id": "uuid"
  }
}
```

### 6.2 刷新 Token

```http
POST /api/v1/auth/refresh
```

```json
{"refresh_token": "jwt"}
```

### 6.3 退出登录

```http
POST /api/v1/auth/logout
```

### 6.4 当前用户

```http
GET /api/v1/me
GET /api/v1/me/permissions
```

---

## 7. 组织、班级、用户与学生接口

### 7.1 接口清单

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/organizations` | super_admin | 查询机构 |
| POST | `/organizations` | super_admin | 创建机构 |
| GET | `/organizations/{organizationId}` | super_admin/org_admin | 机构详情 |
| PATCH | `/organizations/{organizationId}` | super_admin/org_admin | 更新机构 |
| GET | `/classes` | 管理端 | 查询班级 |
| POST | `/classes` | org_admin | 创建班级 |
| PATCH | `/classes/{classId}` | org_admin | 更新班级 |
| GET | `/users` | org_admin | 查询用户 |
| POST | `/users` | org_admin | 创建用户 |
| PATCH | `/users/{userId}` | org_admin | 更新用户 |
| GET | `/students` | counselor/teacher/org_admin | 查询学生 |
| POST | `/students` | counselor/org_admin | 创建学生 |
| GET | `/students/{studentId}` | 有权限角色 | 学生详情 |
| PATCH | `/students/{studentId}` | counselor/org_admin | 更新学生 |
| POST | `/students/{studentId}/guardians` | counselor/org_admin | 绑定监护人 |
| GET | `/students/{studentId}/guardians` | counselor/org_admin | 查询监护人 |
| POST | `/students/{studentId}/assignments` | org_admin/counselor | 分配咨询师 |
| GET | `/students/{studentId}/sessions` | 有权限角色 | 学生测评列表 |
| GET | `/students/{studentId}/reports` | 有权限角色 | 学生报告列表 |

### 7.2 创建学生

```http
POST /api/v1/students
```

```json
{
  "username": "student001",
  "display_name": "张同学",
  "student_no": "PS-QUICK",
  "class_id": "uuid",
  "gender": "male",
  "birth_date": "2014-06-01",
  "school_stage": "primary",
  "grade_level": "五年级"
}
```

### 7.3 学生查询过滤参数

| 参数 | 说明 |
|---|---|
| `organization_id` | 机构 |
| `class_id` | 班级 |
| `grade_level` | 年级 |
| `school_stage` | 学段 |
| `keyword` | 学生编号/姓名 |
| `has_active_session` | 是否有进行中会话 |
| `risk_level` | 仅 counselor/admin 可按报告风险筛选 |

---

## 8. 沙具资产与理论字典接口

### 8.1 接口清单

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/asset-categories` | 登录用户 | 八大沙具分类 |
| GET | `/miniatures` | 登录用户 | 沙具列表，支持分类/关键词/标签 |
| GET | `/miniatures/{miniatureId}` | 登录用户 | 沙具详情 |
| POST | `/admin/miniatures` | admin | 新增沙具 |
| PATCH | `/admin/miniatures/{miniatureId}` | admin | 更新沙具 |
| POST | `/admin/miniatures/{miniatureId}/asset-file` | admin | 绑定素材文件 |
| GET | `/theory-sources` | counselor/admin | 理论来源列表 |
| GET | `/theory-concepts` | counselor/admin | 理论概念列表 |
| GET | `/miniatures/{miniatureId}/theory-mappings` | counselor/admin | 沙具理论映射 |

### 8.2 沙具查询参数

| 参数 | 说明 |
|---|---|
| `category` | 八大分类编码 |
| `keyword` | 名称/编码 |
| `tag` | 主题/原型/文化标签 |
| `is_active` | 是否启用 |
| `page/page_size` | 分页 |

### 8.3 沙具响应

```json
{
  "id": "uuid",
  "code": "building_fence_001",
  "name": "木栅栏",
  "category": "building_home",
  "default_scale": 1,
  "theory_summary": "可作为边界、防御、安全空间构建的探索性观察线索。",
  "asset_file": {
    "file_id": "uuid",
    "download_url": "signed-url"
  },
  "tags": ["boundary_defense", "safety_container"]
}
```

---

## 9. 沙盘会话与过程采集接口

### 9.1 创建会话

```http
POST /api/v1/sessions
```

权限：`counselor`、`teacher`、`org_admin`、`student(本人)`。

```json
{
  "student_id": "uuid",
  "class_id": "uuid",
  "counselor_id": "uuid",
  "environment_meta": {
    "theme": "warm_morandi",
    "sound_enabled": false,
    "weather": "sunny"
  },
  "canvas_meta": {
    "width": 1600,
    "height": 1200,
    "grid": "3x3",
    "view_mode": "oblique45"
  }
}
```

响应：

```json
{
  "session_id": "uuid",
  "session_no": "SP-20261119-0001",
  "status": "draft",
  "started_at": "2026-11-19T10:30:00Z"
}
```

### 9.2 查询会话

```http
GET /api/v1/sessions
GET /api/v1/sessions/{sessionId}
```

过滤参数：`student_id`、`class_id`、`counselor_id`、`status`、`date_from`、`date_to`。

### 9.3 更新会话

```http
PATCH /api/v1/sessions/{sessionId}
```

仅 `draft`、`collecting` 状态允许修改基础元数据。

### 9.4 上传沙盘快照

```http
POST /api/v1/sessions/{sessionId}/snapshots
```

```json
{
  "file_id": "uuid",
  "view_type": "final",
  "is_final": true,
  "width": 1600,
  "height": 1200,
  "captured_at": "2026-11-19T10:40:00Z"
}
```

约束：一个会话只能有一个 `is_final = true` 的快照。

### 9.5 保存地形状态

```http
POST /api/v1/sessions/{sessionId}/terrain-state
```

```json
{
  "heightmap_file_id": "uuid",
  "raise_count": 4,
  "dig_count": 2,
  "dig_water_count": 1,
  "smoothed_count": 1,
  "raised_area_ratio": 0.12,
  "water_area_ratio": 0.08,
  "blank_ratio": 0.37,
  "final_grid_metrics": {
    "center": {"raised_ratio": 0.18, "water_ratio": 0.02}
  }
}
```

### 9.6 批量上报过程事件

见 `4.2 ProcessEventBatchPayload`。

响应：

```json
{
  "accepted_count": 2,
  "duplicated_count": 0,
  "next_expected_seq_no": 3
}
```

### 9.7 保存最终沙盘状态

见 `4.1 SandplayFinalStatePayload`。

成功后将会话状态置为 `collecting` 或等待 `submit`。

### 9.8 提交会话

```http
POST /api/v1/sessions/{sessionId}/submit
```

服务端校验：

1. 会话存在且状态为 `collecting`。
2. 学生存在有效监护人同意记录。
3. 最终快照存在。
4. `final-state` 已保存。
5. 九宫格、沙具、过程指标、自述、成绩单数据完整或明确标记缺失。

响应：

```json
{
  "session_id": "uuid",
  "status": "submitted",
  "submitted_at": "2026-11-19T10:45:00Z"
}
```

---

## 10. 自述与成绩单接口

### 10.1 保存自述

```http
POST /api/v1/sessions/{sessionId}/self-report
```

```json
{
  "author_role": "student",
  "content": "我最近不太想去学校。",
  "mood_tags": ["焦虑", "疲惫"],
  "attachment_file_ids": ["uuid"]
}
```

### 10.2 上传成绩单

```http
POST /api/v1/sessions/{sessionId}/transcripts
```

```json
{
  "source_file_id": "uuid",
  "semester": "2026-2027-1"
}
```

### 10.3 发起 OCR

```http
POST /api/v1/transcripts/{transcriptId}/ocr
```

返回 `202 Accepted`。

### 10.4 查询成绩单

```http
GET /api/v1/transcripts/{transcriptId}
GET /api/v1/transcripts/{transcriptId}/subjects
```

### 10.5 确认成绩单

```http
PUT /api/v1/transcripts/{transcriptId}/confirm
```

```json
{
  "total_score": 778,
  "total_full_score": 980,
  "score_rate": 0.7939,
  "overall_level": "good",
  "subjects": [
    {
      "subject_code": "chinese",
      "subject_name": "语文",
      "full_score": 120,
      "score": 105,
      "score_rate": 0.875,
      "level": "excellent",
      "track": "arts"
    }
  ]
}
```

确认后状态：`confirmed`。AI 分析默认只使用 `confirmed` 成绩单；如使用未确认数据，必须在报告中标明。

---

## 11. AI 分析任务接口

### 11.1 创建分析任务

```http
POST /api/v1/sessions/{sessionId}/analysis-jobs
```

权限：`counselor`、`org_admin`、`super_admin`。  
请求见 `4.3 AnalysisJobCreatePayload`。

响应 `202`：

```json
{
  "job_id": "uuid",
  "status": "queued",
  "session_id": "uuid",
  "poll_url": "/api/v1/analysis-jobs/uuid"
}
```

### 11.2 查询任务

```http
GET /api/v1/analysis-jobs/{jobId}
```

```json
{
  "job_id": "uuid",
  "session_id": "uuid",
  "status": "running",
  "model_name": "multimodal-llm-default",
  "retry_count": 0,
  "queued_at": "2026-11-19T10:46:00Z",
  "started_at": "2026-11-19T10:46:05Z",
  "completed_at": null,
  "error": null
}
```

### 11.3 重试/取消/查询输出

```http
POST /api/v1/analysis-jobs/{jobId}/retry
POST /api/v1/analysis-jobs/{jobId}/cancel
GET  /api/v1/analysis-jobs/{jobId}/output
```

`GET /output` 仅 `counselor/admin` 可用；不得向学生、家长和公开端开放。

---

## 12. 报告审核、发布、分享与导出接口

### 12.1 报告列表与详情

```http
GET /api/v1/reports
GET /api/v1/reports/{reportId}
GET /api/v1/reports/{reportId}?include_risk=true
```

规则：

- `include_risk=true` 仅 `counselor/admin` 可使用。
- 教师默认不得查看 `risk_assessment`。
- 学生/家长端接口不得返回 `risk_assessment`。

### 12.2 修改报告章节

```http
PUT /api/v1/reports/{reportId}/sections/{sectionId}
```

```json
{
  "content": {
    "conclusion": "调整后的发展性建议。",
    "evidence": ["证据 1", "证据 2"]
  },
  "change_note": "咨询师根据访谈补充调整"
}
```

服务端必须写入 `report_revisions`。

### 12.3 审核状态流转

```http
POST /api/v1/reports/{reportId}/submit-review
POST /api/v1/reports/{reportId}/approve
POST /api/v1/reports/{reportId}/reject
POST /api/v1/reports/{reportId}/publish
POST /api/v1/reports/{reportId}/unpublish
```

`reject` 请求：

```json
{
  "reason": "风险研判证据不足，请补充访谈后再审。"
}
```

### 12.4 修订记录

```http
GET /api/v1/reports/{reportId}/revisions
```

### 12.5 导出报告

```http
POST /api/v1/reports/{reportId}/exports
```

```json
{
  "export_type": "pdf",
  "audience": "guardian",
  "include_risk": false
}
```

响应 `202`：

```json
{
  "export_id": "uuid",
  "status": "queued"
}
```

### 12.6 创建分享链接

```http
POST /api/v1/reports/{reportId}/share-links
```

```json
{
  "audience": "guardian",
  "expires_at": "2027-01-01T00:00:00Z",
  "password": "optional-plain-password"
}
```

响应：

```json
{
  "share_link_id": "uuid",
  "share_url": "https://example.com/s/token",
  "audience": "guardian",
  "expires_at": "2027-01-01T00:00:00Z"
}
```

数据库只保存 `token_hash` 和 `password_hash`。

### 12.7 查询/撤销分享链接

```http
GET    /api/v1/reports/{reportId}/share-links
DELETE /api/v1/share-links/{shareLinkId}
```

---

## 13. 公开分享接口

### 13.1 获取脱敏报告

```http
GET /api/v1/public/shared-reports/{shareToken}
```

响应：

```json
{
  "report_no": "PS-QUICK-20261119",
  "student_alias": "PS-QUICK",
  "school_stage": "初中",
  "generated_at": "2026-11-19T11:00:00Z",
  "disclaimer": "发展性心理评估参考，非临床诊断；所有探索性假设需访谈确认。",
  "overview": {},
  "imagery_analysis": [],
  "six_dimensions": [],
  "academic_evaluation": {},
  "interview_suggestions": [],
  "career_strengths": [],
  "training_modules": [],
  "general_advice": {}
}
```

明确禁止返回：

- `risk_assessment`
- 学生真实姓名、手机号、身份证号
- 成绩单原图下载地址
- AI 原始 Prompt/响应
- 咨询师内部审核意见

### 13.2 分享密码校验

```http
POST /api/v1/public/shared-reports/{shareToken}/verify
```

```json
{"password": "optional-plain-password"}
```

---

## 14. 数据统计接口

所有统计接口默认仅返回聚合数据，不返回学生明文名单；若返回名单，仅 `counselor/admin` 可见。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/analytics/overview` | admin/counselor/teacher | 总览：人数、报告数、完成率 |
| GET | `/analytics/risk-distribution` | admin/counselor | L1-L4 风险分布 |
| GET | `/analytics/top-miniatures` | admin/counselor/teacher | Top 沙具 |
| GET | `/analytics/grid-heatmap` | admin/counselor/teacher | 九宫格热力 |
| GET | `/analytics/training-module-needs` | admin/counselor/teacher | 训练模块需求分布 |
| GET | `/analytics/academic-subject-distribution` | admin/counselor/teacher | 学科优势/薄弱分布 |

公共过滤参数：

| 参数 | 说明 |
|---|---|
| `organization_id` | 机构 |
| `class_id` | 班级 |
| `grade_level` | 年级 |
| `school_stage` | 学段 |
| `date_from/date_to` | 时间范围 |
| `report_status` | 默认 `published` |

---

## 15. 审计与系统接口

```http
GET /api/v1/audit-logs
GET /api/v1/report-access-logs
GET /api/v1/system/health
```

`audit-logs` 查询参数：

| 参数 | 说明 |
|---|---|
| `user_id` | 操作人 |
| `action` | 操作类型 |
| `resource_type` | 资源类型 |
| `resource_id` | 资源 ID |
| `date_from/date_to` | 时间范围 |

---

## 16. 错误码契约

| HTTP | code | 说明 |
|---:|---|---|
| 400 | `VALIDATION_INVALID_PAYLOAD` | 请求 JSON 不符合 Schema |
| 400 | `VALIDATION_INVALID_GRID_CELL` | 九宫格编码非法 |
| 400 | `VALIDATION_INVALID_SCORE` | 分数、得分率非法 |
| 401 | `AUTH_UNAUTHORIZED` | 未登录或 Token 无效 |
| 401 | `AUTH_TOKEN_EXPIRED` | Token 过期 |
| 403 | `PERM_FORBIDDEN` | 无权限 |
| 403 | `PERM_RISK_SECTION_FORBIDDEN` | 无权查看风险研判 |
| 403 | `CONSENT_REQUIRED` | 缺少有效知情同意 |
| 404 | `RESOURCE_NOT_FOUND` | 资源不存在 |
| 409 | `SESSION_INVALID_STATE` | 会话状态不允许当前操作 |
| 409 | `SESSION_FINAL_SNAPSHOT_EXISTS` | 最终快照已存在 |
| 409 | `AI_JOB_RUNNING` | 已有分析任务运行中 |
| 409 | `REPORT_INVALID_STATE` | 报告状态不允许当前操作 |
| 409 | `TRANSCRIPT_ALREADY_CONFIRMED` | 成绩单已确认 |
| 413 | `FILE_TOO_LARGE` | 文件过大 |
| 415 | `FILE_UNSUPPORTED_TYPE` | 文件类型不支持 |
| 422 | `AI_OUTPUT_SCHEMA_INVALID` | AI 输出不符合报告 Schema |
| 429 | `RATE_LIMITED` | 请求频率超限 |
| 500 | `INTERNAL_ERROR` | 服务内部错误 |

---

## 17. 隐私、伦理与输出约束

1. 所有报告必须包含：

```text
发展性心理评估参考，非临床诊断；所有探索性假设需访谈确认。
```

2. 禁止 AI 输出：
   - 临床诊断名词；
   - 对学生人格、能力、家庭关系的确定性否定；
   - 病理化、羞辱性、标签化措辞；
   - 未经授权的医学建议。

3. 沙具象征解释必须使用：
   - “可能提示”
   - “可作为观察线索”
   - “需结合访谈确认”
   - “发展性假设”

4. 理论引用必须能追溯到数据库中的 `theory_concepts` 和 `theory_sources`。

5. 未成年人测评必须先存在有效 `consent_records`。

6. 报告查看、风险查看、导出、分享访问必须写入审计日志。

---

## 18. 理论来源对齐

当前契约中的理论术语与数据库种子数据对齐：

| 理论来源 | 用途 |
|---|---|
| 张日昇《箱庭疗法》 | 自由与受保护空间、母子一体性、自我治愈力、制作过程记录、象征配置、边界防御、九宫格观察 |
| 申荷永《心理分析：理解与体验》 | 理解与体验、心性与感应、意象体现、非评判伦理、三层心理发展目标 |
| 申荷永《荣格与分析心理学》 | 集体无意识、原型、人格面具、阴影、智慧老人、自性化、象征性分析、积极想象 |

在线核验来源以数据库 `theory_sources` 种子数据为准。

---

## 19. 版本兼容规则

- 新增可选字段：向后兼容，不升大版本。
- 修改字段含义、删除字段、改变枚举：必须升级 `schema_version`。
- `SandplayFinalStatePayload.schema_version` 初始固定为 `1.0`。
- AI 输出 `AssessmentReportOutput` 初始固定为 `1.0`。
- 前端提交未知字段时，服务端可忽略并记录到 `client_meta.unknown_fields`。

---

## 20. 交付检查清单

- [x] 覆盖学生端、沙盘端、咨询师端、管理员端、公开分享端、AI 引擎端。
- [x] 覆盖沙盘过程事件、最终状态、九宫格、地形、沙具、成绩单、AI 分析、报告审核、分享导出、统计看板。
- [x] 明确九维风险仅咨询师可见。
- [x] 明确公开分享页脱敏字段。
- [x] 明确会话、OCR、AI 任务、报告审核状态机。
- [x] 明确统一错误码和权限矩阵。
