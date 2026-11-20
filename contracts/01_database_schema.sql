-- =====================================================================
-- 心理沙盘学习动力发展性评估系统 - PostgreSQL 15+ 数据库契约
-- 版本: v1.0
-- 依据: 全局架构与设计总纲、四大模块提示词、三本书理论来源、样例报告
-- 说明: 本文件只包含数据库结构、约束、索引、视图和基础字典，不包含业务实现代码
-- =====================================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS sandplay;
SET search_path TO sandplay, public;

-- ---------------------------------------------------------------------
-- 0. 通用函数
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION set_updated_at() IS '通用 updated_at 自动更新时间触发器函数';

-- ---------------------------------------------------------------------
-- 1. 文件、组织、用户与权限
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS file_objects (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id        uuid,
  bucket          varchar(128) NOT NULL DEFAULT 'local',
  object_key      varchar(512) NOT NULL,
  file_name       varchar(255) NOT NULL,
  mime_type       varchar(128) NOT NULL,
  size_bytes      bigint NOT NULL CHECK (size_bytes >= 0),
  sha256          varchar(64) NOT NULL,
  visibility      varchar(32) NOT NULL DEFAULT 'private'
                  CHECK (visibility IN ('private', 'organization', 'counselor_only', 'public')),
  metadata        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  created_at      timestamptz NOT NULL DEFAULT now(),
  deleted_at      timestamptz,
  CONSTRAINT uq_file_objects_bucket_key UNIQUE (bucket, object_key)
);

COMMENT ON TABLE file_objects IS '统一文件元数据表：沙盘截图、成绩单、PDF、Heightmap、沙具素材等';
COMMENT ON COLUMN file_objects.visibility IS '文件可见性：private/organization/counselor_only/public';
COMMENT ON COLUMN file_objects.sha256 IS '文件 SHA-256，用于完整性校验与去重';

CREATE TABLE IF NOT EXISTS organizations (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code            varchar(64) NOT NULL UNIQUE,
  name            varchar(128) NOT NULL,
  org_type        varchar(32) NOT NULL DEFAULT 'school'
                  CHECK (org_type IN ('school', 'agency', 'hospital', 'platform', 'other')),
  status          varchar(32) NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active', 'disabled', 'archived')),
  contact_name    varchar(64),
  contact_phone   varchar(32),
  address         text,
  settings        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(settings) = 'object'),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  deleted_at      timestamptz
);

COMMENT ON TABLE organizations IS '学校、教育机构或平台租户表';

CREATE TABLE IF NOT EXISTS classes (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  code            varchar(64) NOT NULL,
  name            varchar(128) NOT NULL,
  academic_year   varchar(16) NOT NULL,
  grade_level     varchar(32) NOT NULL,
  status          varchar(32) NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active', 'graduated', 'archived')),
  metadata        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_classes_org_code UNIQUE (organization_id, code)
);

COMMENT ON TABLE classes IS '班级表：按学校/机构、学年、年级和班级编码组织学生';

CREATE TABLE IF NOT EXISTS users (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid REFERENCES organizations(id) ON DELETE SET NULL,
  username        varchar(64) NOT NULL UNIQUE,
  password_hash   varchar(255),
  display_name    varchar(64) NOT NULL,
  role            varchar(32) NOT NULL
                  CHECK (role IN ('super_admin', 'org_admin', 'counselor', 'teacher', 'student', 'guardian')),
  status          varchar(32) NOT NULL DEFAULT 'active'
                  CHECK (status IN ('pending', 'active', 'disabled', 'archived')),
  phone           varchar(32),
  email           varchar(128),
  avatar_file_id  uuid REFERENCES file_objects(id) ON DELETE SET NULL,
  last_login_at   timestamptz,
  settings        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(settings) = 'object'),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  deleted_at      timestamptz
);

COMMENT ON TABLE users IS '统一账号表，覆盖管理员、咨询师、教师、学生、家长等角色';
COMMENT ON COLUMN users.role IS '系统角色：super_admin/org_admin/counselor/teacher/student/guardian';

CREATE TABLE IF NOT EXISTS student_profiles (
  user_id         uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  student_no      varchar(64) NOT NULL UNIQUE,
  class_id        uuid REFERENCES classes(id) ON DELETE SET NULL,
  gender          varchar(16) NOT NULL DEFAULT 'unknown'
                  CHECK (gender IN ('male', 'female', 'other', 'unknown')),
  birth_date      date,
  school_stage    varchar(32) NOT NULL DEFAULT 'primary'
                  CHECK (school_stage IN ('primary', 'junior', 'senior', 'other')),
  grade_level     varchar(32),
  guardian_note   text,
  metadata        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE student_profiles IS '学生扩展档案，学生编号优先于真实姓名用于业务展示';

CREATE TABLE IF NOT EXISTS guardian_links (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id      uuid NOT NULL REFERENCES student_profiles(user_id) ON DELETE CASCADE,
  guardian_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  relationship    varchar(32) NOT NULL,
  is_primary      boolean NOT NULL DEFAULT false,
  contact_priority integer NOT NULL DEFAULT 1 CHECK (contact_priority > 0),
  created_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_guardian_links UNIQUE (student_id, guardian_id, relationship)
);

COMMENT ON TABLE guardian_links IS '学生与监护人关系表';

CREATE TABLE IF NOT EXISTS counselor_assignments (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  counselor_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  organization_id uuid REFERENCES organizations(id) ON DELETE CASCADE,
  class_id        uuid REFERENCES classes(id) ON DELETE CASCADE,
  student_id      uuid REFERENCES student_profiles(user_id) ON DELETE CASCADE,
  assignment_scope varchar(32) NOT NULL
                  CHECK (assignment_scope IN ('organization', 'class', 'student')),
  status          varchar(32) NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active', 'paused', 'ended')),
  starts_at       timestamptz NOT NULL DEFAULT now(),
  ends_at         timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_counselor_assignment_scope CHECK (
    (assignment_scope = 'organization' AND organization_id IS NOT NULL) OR
    (assignment_scope = 'class' AND class_id IS NOT NULL) OR
    (assignment_scope = 'student' AND student_id IS NOT NULL)
  ),
  CONSTRAINT ck_counselor_assignment_time CHECK (ends_at IS NULL OR ends_at > starts_at)
);

COMMENT ON TABLE counselor_assignments IS '咨询师负责范围：机构、班级或单个学生';

CREATE TABLE IF NOT EXISTS consent_records (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id      uuid NOT NULL REFERENCES student_profiles(user_id) ON DELETE CASCADE,
  guardian_id     uuid REFERENCES users(id) ON DELETE SET NULL,
  consent_type    varchar(64) NOT NULL DEFAULT 'sandplay_assessment',
  status          varchar(32) NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'signed', 'revoked', 'expired')),
  signed_at       timestamptz,
  expires_at      timestamptz,
  document_file_id uuid REFERENCES file_objects(id) ON DELETE SET NULL,
  notes           text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE consent_records IS '未成年人测评知情同意与监护人授权记录';

-- ---------------------------------------------------------------------
-- 2. 理论来源、沙具资产与心理标签
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS theory_sources (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code             varchar(64) NOT NULL UNIQUE,
  title            varchar(255) NOT NULL,
  author           varchar(128),
  publisher        varchar(128),
  published_on     date,
  isbn             varchar(32),
  edition          varchar(64),
  source_type      varchar(64) NOT NULL
                   CHECK (source_type IN ('book', 'publisher_page', 'academic_review', 'university_course', 'university_publication', 'institution_page', 'library_catalog')),
  url              text,
  local_path       text,
  reliability_level varchar(16) NOT NULL DEFAULT 'high'
                   CHECK (reliability_level IN ('high', 'medium', 'low')),
  verified_at      timestamptz,
  notes            text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE theory_sources IS '理论来源表：三本书、本地路径、出版社/高校/图书馆/科研机构链接与可信级别';

CREATE TABLE IF NOT EXISTS theory_concepts (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code              varchar(64) NOT NULL UNIQUE,
  name_cn           varchar(128) NOT NULL,
  name_en           varchar(128),
  source_id         uuid NOT NULL REFERENCES theory_sources(id) ON DELETE RESTRICT,
  chapter           varchar(128),
  definition_summary text NOT NULL,
  application_scope text,
  prohibited_boundary text,
  prompt_allowed    boolean NOT NULL DEFAULT true,
  metadata          jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE theory_concepts IS '理论概念字典：自我治愈力、母子一体性、原型、阴影、自性化、感应等';

CREATE TABLE IF NOT EXISTS asset_categories (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code        varchar(64) NOT NULL UNIQUE,
  name        varchar(128) NOT NULL,
  description text,
  sort_order  integer NOT NULL DEFAULT 0,
  is_active   boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE asset_categories IS '沙具八大心理学分类字典';

CREATE TABLE IF NOT EXISTS miniatures (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code            varchar(64) NOT NULL UNIQUE,
  name            varchar(128) NOT NULL,
  category_id     uuid NOT NULL REFERENCES asset_categories(id) ON DELETE RESTRICT,
  default_scale   numeric(10,4) NOT NULL DEFAULT 1.0 CHECK (default_scale > 0),
  default_width   numeric(10,2),
  default_height  numeric(10,2),
  theory_summary  text,
  image_prompt    text,
  asset_file_id   uuid REFERENCES file_objects(id) ON DELETE SET NULL,
  is_active       boolean NOT NULL DEFAULT true,
  metadata        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE miniatures IS '心理沙盘沙具主档：500+ 沙具的分类、象征摘要与生图提示词';

CREATE TABLE IF NOT EXISTS tags (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code       varchar(64) NOT NULL UNIQUE,
  name       varchar(128) NOT NULL,
  tag_type   varchar(32) NOT NULL DEFAULT 'theme'
             CHECK (tag_type IN ('theme', 'archetype', 'culture', 'emotion', 'space', 'learning')),
  created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE tags IS '通用标签字典：主题、原型、文化、情绪、空间、学习等';

CREATE TABLE IF NOT EXISTS miniature_tags (
  miniature_id uuid NOT NULL REFERENCES miniatures(id) ON DELETE CASCADE,
  tag_id       uuid NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  weight       numeric(5,2) NOT NULL DEFAULT 1.0 CHECK (weight >= 0),
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (miniature_id, tag_id)
);

COMMENT ON TABLE miniature_tags IS '沙具与标签多对多映射表';

CREATE TABLE IF NOT EXISTS miniature_theory_mappings (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  miniature_id   uuid NOT NULL REFERENCES miniatures(id) ON DELETE CASCADE,
  concept_id     uuid NOT NULL REFERENCES theory_concepts(id) ON DELETE CASCADE,
  mapping_reason text NOT NULL,
  evidence_note  text,
  weight         numeric(5,2) NOT NULL DEFAULT 1.0 CHECK (weight >= 0),
  created_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_miniature_theory_mapping UNIQUE (miniature_id, concept_id)
);

COMMENT ON TABLE miniature_theory_mappings IS '沙具与三本书理论概念的多对多映射，含映射理由与证据说明';

-- ---------------------------------------------------------------------
-- 3. 沙盘会话、九宫格、地形与过程事件
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS grid_cells (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code            varchar(32) NOT NULL UNIQUE,
  name            varchar(32) NOT NULL,
  row_index       integer NOT NULL CHECK (row_index BETWEEN 1 AND 3),
  col_index       integer NOT NULL CHECK (col_index BETWEEN 1 AND 3),
  spatial_meaning text,
  sort_order      integer NOT NULL DEFAULT 0
);

COMMENT ON TABLE grid_cells IS '九宫格区域字典，空间意义仅作发展性观察，不作临床诊断';

CREATE TABLE IF NOT EXISTS assessment_sessions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_no      varchar(64) NOT NULL UNIQUE,
  student_id      uuid NOT NULL REFERENCES student_profiles(user_id) ON DELETE RESTRICT,
  counselor_id    uuid REFERENCES users(id) ON DELETE SET NULL,
  organization_id uuid REFERENCES organizations(id) ON DELETE SET NULL,
  class_id        uuid REFERENCES classes(id) ON DELETE SET NULL,
  status          varchar(32) NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft', 'collecting', 'submitted', 'analyzing', 'analyzed', 'report_review', 'published', 'archived', 'failed')),
  started_at      timestamptz NOT NULL DEFAULT now(),
  ended_at        timestamptz,
  duration_seconds integer CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
  environment_meta jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(environment_meta) = 'object'),
  canvas_meta     jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(canvas_meta) = 'object'),
  client_meta     jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(client_meta) = 'object'),
  submitted_at    timestamptz,
  archived_at     timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_assessment_sessions_time CHECK (ended_at IS NULL OR ended_at >= started_at)
);

COMMENT ON TABLE assessment_sessions IS '一次心理沙盘测评会话主表';

CREATE TABLE IF NOT EXISTS sandplay_snapshots (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id  uuid NOT NULL REFERENCES assessment_sessions(id) ON DELETE CASCADE,
  file_id     uuid NOT NULL REFERENCES file_objects(id) ON DELETE RESTRICT,
  view_type   varchar(32) NOT NULL DEFAULT 'top'
              CHECK (view_type IN ('top', 'oblique45', 'front', 'process', 'final')),
  is_final    boolean NOT NULL DEFAULT false,
  captured_at timestamptz NOT NULL DEFAULT now(),
  width       integer CHECK (width IS NULL OR width > 0),
  height      integer CHECK (height IS NULL OR height > 0),
  metadata    jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  created_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE sandplay_snapshots IS '沙盘过程快照与最终高清俯视图';

CREATE TABLE IF NOT EXISTS terrain_states (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id         uuid NOT NULL UNIQUE REFERENCES assessment_sessions(id) ON DELETE CASCADE,
  heightmap_file_id  uuid REFERENCES file_objects(id) ON DELETE SET NULL,
  raise_count        integer NOT NULL DEFAULT 0 CHECK (raise_count >= 0),
  dig_count          integer NOT NULL DEFAULT 0 CHECK (dig_count >= 0),
  dig_water_count    integer NOT NULL DEFAULT 0 CHECK (dig_water_count >= 0),
  smoothed_count     integer NOT NULL DEFAULT 0 CHECK (smoothed_count >= 0),
  raised_area_ratio  numeric(6,5) NOT NULL DEFAULT 0 CHECK (raised_area_ratio BETWEEN 0 AND 1),
  water_area_ratio   numeric(6,5) NOT NULL DEFAULT 0 CHECK (water_area_ratio BETWEEN 0 AND 1),
  blank_ratio        numeric(6,5) NOT NULL DEFAULT 0 CHECK (blank_ratio BETWEEN 0 AND 1),
  final_grid_metrics jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(final_grid_metrics) = 'object'),
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE terrain_states IS '沙盘地形最终状态：堆沙、挖沙、挖水、抚平、留白和九宫格地形指标';

CREATE TABLE IF NOT EXISTS sandplay_items (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id   uuid NOT NULL REFERENCES assessment_sessions(id) ON DELETE CASCADE,
  miniature_id uuid NOT NULL REFERENCES miniatures(id) ON DELETE RESTRICT,
  instance_no  integer NOT NULL CHECK (instance_no > 0),
  x            numeric(10,6) NOT NULL CHECK (x BETWEEN 0 AND 1),
  y            numeric(10,6) NOT NULL CHECK (y BETWEEN 0 AND 1),
  z            numeric(10,6) NOT NULL DEFAULT 0,
  scale        numeric(10,4) NOT NULL DEFAULT 1.0 CHECK (scale > 0),
  rotation     numeric(8,3) NOT NULL DEFAULT 0 CHECK (rotation >= 0 AND rotation < 360),
  flipped      boolean NOT NULL DEFAULT false,
  grid_cell_id uuid REFERENCES grid_cells(id) ON DELETE SET NULL,
  cluster_id   varchar(64),
  is_enclosed  boolean NOT NULL DEFAULT false,
  is_final     boolean NOT NULL DEFAULT true,
  placed_at    timestamptz NOT NULL DEFAULT now(),
  removed_at   timestamptz,
  metadata     jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_sandplay_items_instance UNIQUE (session_id, instance_no)
);

COMMENT ON TABLE sandplay_items IS '沙盘沙具实例：坐标、缩放、旋转、翻转、九宫格、聚类和边界包围状态';

CREATE TABLE IF NOT EXISTS process_events (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id    uuid NOT NULL REFERENCES assessment_sessions(id) ON DELETE CASCADE,
  seq_no        integer NOT NULL CHECK (seq_no > 0),
  event_type    varchar(32) NOT NULL
                CHECK (event_type IN ('raise_sand', 'dig_sand', 'dig_water', 'smooth_sand', 'place', 'move', 'scale', 'rotate', 'flip', 'remove', 'undo', 'redo', 'clear', 'snapshot', 'custom')),
  tool_type     varchar(64),
  target_item_id uuid REFERENCES sandplay_items(id) ON DELETE SET NULL,
  payload       jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
  client_ts     timestamptz,
  server_ts     timestamptz NOT NULL DEFAULT now(),
  created_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_process_events_session_seq UNIQUE (session_id, seq_no)
);

COMMENT ON TABLE process_events IS '沙盘制作过程事件流：可按 session_id + seq_no 回放过程';

-- ---------------------------------------------------------------------
-- 4. 自述、成绩单与会话附件
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS self_reports (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id     uuid NOT NULL REFERENCES assessment_sessions(id) ON DELETE CASCADE,
  author_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  author_role    varchar(32) NOT NULL
                 CHECK (author_role IN ('student', 'guardian', 'teacher', 'counselor')),
  content        text NOT NULL,
  mood_tags      text[] NOT NULL DEFAULT '{}'::text[],
  attachment_file_ids uuid[] NOT NULL DEFAULT '{}'::uuid[],
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_self_reports_author UNIQUE (session_id, author_role)
);

COMMENT ON TABLE self_reports IS '受测者、家长、教师或咨询师的自述与补充说明';

CREATE TABLE IF NOT EXISTS academic_transcripts (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id       uuid NOT NULL REFERENCES assessment_sessions(id) ON DELETE CASCADE,
  source_file_id   uuid REFERENCES file_objects(id) ON DELETE SET NULL,
  ocr_status       varchar(32) NOT NULL DEFAULT 'uploaded'
                   CHECK (ocr_status IN ('uploaded', 'processing', 'parsed', 'confirmed', 'failed')),
  total_score      numeric(10,2) CHECK (total_score IS NULL OR total_score >= 0),
  total_full_score numeric(10,2) CHECK (total_full_score IS NULL OR total_full_score > 0),
  score_rate       numeric(6,5) CHECK (score_rate IS NULL OR score_rate BETWEEN 0 AND 1),
  overall_level    varchar(32)
                   CHECK (overall_level IS NULL OR overall_level IN ('excellent', 'good', 'pass', 'fail', 'unknown')),
  structured_data  jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(structured_data) = 'object'),
  confirmed_by     uuid REFERENCES users(id) ON DELETE SET NULL,
  confirmed_at     timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_transcript_total CHECK (total_score IS NULL OR total_full_score IS NULL OR total_score <= total_full_score)
);

COMMENT ON TABLE academic_transcripts IS '学业成绩单主表：原图、OCR 状态、总分、得分率和确认状态';

CREATE TABLE IF NOT EXISTS transcript_subjects (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  transcript_id uuid NOT NULL REFERENCES academic_transcripts(id) ON DELETE CASCADE,
  subject_code  varchar(64) NOT NULL,
  subject_name  varchar(64) NOT NULL,
  full_score    numeric(10,2) NOT NULL CHECK (full_score > 0),
  score         numeric(10,2) NOT NULL CHECK (score >= 0),
  score_rate    numeric(6,5) NOT NULL CHECK (score_rate BETWEEN 0 AND 1),
  level         varchar(32) NOT NULL DEFAULT 'unknown'
                CHECK (level IN ('excellent', 'good', 'pass', 'fail', 'unknown')),
  track         varchar(32) NOT NULL DEFAULT 'unknown'
                CHECK (track IN ('arts', 'science', 'general', 'unknown')),
  semester      varchar(32),
  metadata      jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  created_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_transcript_subject UNIQUE (transcript_id, subject_code),
  CONSTRAINT ck_subject_score CHECK (score <= full_score)
);

COMMENT ON TABLE transcript_subjects IS '成绩单科目明细：科目、满分、得分、得分率、等级、文理方向';

CREATE TABLE IF NOT EXISTS session_attachments (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id      uuid NOT NULL REFERENCES assessment_sessions(id) ON DELETE CASCADE,
  file_id         uuid NOT NULL REFERENCES file_objects(id) ON DELETE RESTRICT,
  attachment_type varchar(64) NOT NULL DEFAULT 'other',
  uploader_id     uuid REFERENCES users(id) ON DELETE SET NULL,
  visibility      varchar(32) NOT NULL DEFAULT 'counselor_only'
                  CHECK (visibility IN ('private', 'organization', 'counselor_only', 'public')),
  note            text,
  created_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE session_attachments IS '沙盘会话补充附件：教师反馈、家长说明、访谈材料等';

-- ---------------------------------------------------------------------
-- 5. AI 提示词、分析任务与输入输出留档
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ai_prompt_templates (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code              varchar(64) NOT NULL UNIQUE,
  version           varchar(32) NOT NULL,
  name              varchar(128) NOT NULL,
  system_prompt     text NOT NULL,
  theory_source_ids uuid[] NOT NULL DEFAULT '{}'::uuid[],
  report_schema     jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(report_schema) = 'object'),
  status            varchar(32) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'active', 'deprecated')),
  effective_from    timestamptz NOT NULL DEFAULT now(),
  effective_to      timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_ai_prompt_code_version UNIQUE (code, version)
);

COMMENT ON TABLE ai_prompt_templates IS 'LLM 评估提示词模板与版本管理';

CREATE TABLE IF NOT EXISTS ai_analysis_jobs (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id        uuid NOT NULL REFERENCES assessment_sessions(id) ON DELETE CASCADE,
  prompt_template_id uuid REFERENCES ai_prompt_templates(id) ON DELETE SET NULL,
  model_name        varchar(128) NOT NULL,
  status            varchar(32) NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'retrying', 'cancelled')),
  input_hash        varchar(64) NOT NULL,
  request_payload   jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(request_payload) = 'object'),
  response_payload  jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(response_payload) = 'object'),
  error_code        varchar(64),
  error_message     text,
  retry_count       integer NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
  queued_at         timestamptz NOT NULL DEFAULT now(),
  started_at        timestamptz,
  completed_at      timestamptz,
  created_by        uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE ai_analysis_jobs IS 'AI 沙盘分析异步任务表';

CREATE TABLE IF NOT EXISTS ai_analysis_inputs (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id       uuid NOT NULL REFERENCES ai_analysis_jobs(id) ON DELETE CASCADE,
  input_type   varchar(64) NOT NULL
               CHECK (input_type IN ('snapshot', 'final_state', 'process_metrics', 'self_report', 'transcript', 'prompt', 'theory_context', 'other')),
  content_json jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(content_json) = 'object'),
  file_id      uuid REFERENCES file_objects(id) ON DELETE SET NULL,
  content_hash varchar(64) NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE ai_analysis_inputs IS 'AI 分析输入快照，保证报告生成后可追溯';

CREATE TABLE IF NOT EXISTS ai_analysis_outputs (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id             uuid NOT NULL REFERENCES ai_analysis_jobs(id) ON DELETE CASCADE,
  output_json        jsonb NOT NULL CHECK (jsonb_typeof(output_json) = 'object'),
  schema_valid       boolean NOT NULL DEFAULT false,
  validation_errors  jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(validation_errors) = 'array'),
  confidence_overall varchar(16)
                     CHECK (confidence_overall IS NULL OR confidence_overall IN ('high', 'medium', 'low')),
  disclaimer         text NOT NULL DEFAULT '发展性心理评估参考，非临床诊断；所有探索性假设需访谈确认。',
  created_at         timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE ai_analysis_outputs IS 'AI 原始输出、Schema 校验结果和整体置信度';

-- ---------------------------------------------------------------------
-- 6. 报告章节、风险研判、审核、分享与导出
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS report_section_templates (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code            varchar(64) NOT NULL UNIQUE,
  title           varchar(128) NOT NULL,
  sort_order      integer NOT NULL,
  counselor_only  boolean NOT NULL DEFAULT false,
  schema_hint     jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(schema_hint) = 'object'),
  created_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE report_section_templates IS '报告九大章节模板字典';

CREATE TABLE IF NOT EXISTS assessment_reports (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_no              varchar(64) NOT NULL UNIQUE,
  session_id             uuid NOT NULL REFERENCES assessment_sessions(id) ON DELETE RESTRICT,
  ai_job_id              uuid REFERENCES ai_analysis_jobs(id) ON DELETE SET NULL,
  version                integer NOT NULL CHECK (version > 0),
  status                 varchar(32) NOT NULL DEFAULT 'draft'
                         CHECK (status IN ('draft', 'reviewing', 'rejected', 'approved', 'published', 'archived')),
  report_json            jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(report_json) = 'object'),
  disclaimer             text NOT NULL DEFAULT '发展性心理评估参考，非临床诊断；所有探索性假设需访谈确认。',
  generated_at           timestamptz,
  submitted_for_review_at timestamptz,
  reviewed_by            uuid REFERENCES users(id) ON DELETE SET NULL,
  reviewed_at            timestamptz,
  review_note            text,
  published_by           uuid REFERENCES users(id) ON DELETE SET NULL,
  published_at           timestamptz,
  archived_at            timestamptz,
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_assessment_reports_version UNIQUE (session_id, version)
);

COMMENT ON TABLE assessment_reports IS '评估报告主表：完整 JSON、审核状态、发布状态和免责声明';

CREATE TABLE IF NOT EXISTS report_sections (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id      uuid NOT NULL REFERENCES assessment_reports(id) ON DELETE CASCADE,
  template_id    uuid REFERENCES report_section_templates(id) ON DELETE SET NULL,
  section_code   varchar(64) NOT NULL,
  title          varchar(128) NOT NULL,
  content        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(content) = 'object'),
  counselor_only boolean NOT NULL DEFAULT false,
  sort_order     integer NOT NULL DEFAULT 0,
  updated_by     uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_report_sections UNIQUE (report_id, section_code)
);

COMMENT ON TABLE report_sections IS '报告九大章节结构化存储';

CREATE TABLE IF NOT EXISTS evaluation_dimensions (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code             varchar(64) NOT NULL UNIQUE,
  name             varchar(128) NOT NULL,
  theory_framework text,
  description      text,
  sort_order       integer NOT NULL DEFAULT 0,
  created_at       timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE evaluation_dimensions IS '六维学习动力发展性评估维度字典';

CREATE TABLE IF NOT EXISTS report_dimension_assessments (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id          uuid NOT NULL REFERENCES assessment_reports(id) ON DELETE CASCADE,
  dimension_id       uuid NOT NULL REFERENCES evaluation_dimensions(id) ON DELETE RESTRICT,
  confidence         varchar(16) NOT NULL DEFAULT 'medium'
                     CHECK (confidence IN ('high', 'medium', 'low')),
  conclusion         text NOT NULL,
  theory             text NOT NULL,
  evidence           text[] NOT NULL DEFAULT '{}'::text[],
  abilities_to_improve text[] NOT NULL DEFAULT '{}'::text[],
  target_module_ids  uuid[] NOT NULL DEFAULT '{}'::uuid[],
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_report_dimension UNIQUE (report_id, dimension_id)
);

COMMENT ON TABLE report_dimension_assessments IS '六维方向判定与训练模块指向明细';

CREATE TABLE IF NOT EXISTS risk_assessments (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id      uuid NOT NULL REFERENCES assessment_reports(id) ON DELETE CASCADE,
  dimension_code varchar(64) NOT NULL,
  dimension_name varchar(64) NOT NULL,
  level          varchar(8) NOT NULL CHECK (level IN ('L1', 'L2', 'L3', 'L4')),
  conclusion     text NOT NULL,
  evidence       text NOT NULL,
  norm_note      text,
  counselor_only boolean NOT NULL DEFAULT true CHECK (counselor_only = true),
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_risk_assessment UNIQUE (report_id, dimension_code)
);

COMMENT ON TABLE risk_assessments IS '九维风险研判明细，仅咨询师可见';

CREATE TABLE IF NOT EXISTS interview_suggestions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id   uuid NOT NULL REFERENCES assessment_reports(id) ON DELETE CASCADE,
  target_role varchar(32) NOT NULL CHECK (target_role IN ('student', 'guardian', 'teacher')),
  topic       varchar(128) NOT NULL,
  question    text NOT NULL,
  priority    integer NOT NULL DEFAULT 1 CHECK (priority > 0),
  created_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE interview_suggestions IS '访谈建议：面向学生、家长、教师的核心话题与提问';

CREATE TABLE IF NOT EXISTS career_strengths (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id  uuid NOT NULL REFERENCES assessment_reports(id) ON DELETE CASCADE,
  strength   text NOT NULL,
  direction  text NOT NULL,
  actions    jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(actions) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE career_strengths IS '职业发展优势与老师/家长/学生三方行动建议';

CREATE TABLE IF NOT EXISTS training_modules (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code             varchar(64) NOT NULL UNIQUE,
  name             varchar(128) NOT NULL,
  target_abilities text[] NOT NULL DEFAULT '{}'::text[],
  training_logic   text,
  forms            text[] NOT NULL DEFAULT '{}'::text[],
  sort_order       integer NOT NULL DEFAULT 0,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE training_modules IS '六大学习能力训练模块字典';

CREATE TABLE IF NOT EXISTS report_training_recommendations (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id    uuid NOT NULL REFERENCES assessment_reports(id) ON DELETE CASCADE,
  module_id    uuid NOT NULL REFERENCES training_modules(id) ON DELETE RESTRICT,
  dimension_id uuid REFERENCES evaluation_dimensions(id) ON DELETE SET NULL,
  reason       text NOT NULL,
  actions      jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(actions) = 'object'),
  priority     integer NOT NULL DEFAULT 1 CHECK (priority > 0),
  created_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_report_training_module UNIQUE (report_id, module_id, dimension_id)
);

COMMENT ON TABLE report_training_recommendations IS '报告与训练模块、评估维度之间的推荐关系';

CREATE TABLE IF NOT EXISTS report_theory_citations (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id    uuid NOT NULL REFERENCES assessment_reports(id) ON DELETE CASCADE,
  section_id   uuid REFERENCES report_sections(id) ON DELETE SET NULL,
  concept_id   uuid NOT NULL REFERENCES theory_concepts(id) ON DELETE RESTRICT,
  citation_note text NOT NULL,
  source_excerpt text,
  created_at   timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE report_theory_citations IS '报告结论与理论概念之间的引用追溯';

CREATE TABLE IF NOT EXISTS report_revisions (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id      uuid NOT NULL REFERENCES assessment_reports(id) ON DELETE CASCADE,
  section_id     uuid REFERENCES report_sections(id) ON DELETE SET NULL,
  editor_id      uuid REFERENCES users(id) ON DELETE SET NULL,
  before_content jsonb NOT NULL DEFAULT '{}'::jsonb,
  after_content  jsonb NOT NULL DEFAULT '{}'::jsonb,
  change_note    text,
  created_at     timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE report_revisions IS '咨询师人工修订报告的 before/after 留痕';

CREATE TABLE IF NOT EXISTS share_links (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id      uuid NOT NULL REFERENCES assessment_reports(id) ON DELETE CASCADE,
  token_hash     varchar(128) NOT NULL UNIQUE,
  audience       varchar(32) NOT NULL DEFAULT 'guardian'
                 CHECK (audience IN ('student', 'guardian', 'teacher', 'public')),
  status         varchar(32) NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active', 'revoked', 'expired')),
  expires_at     timestamptz,
  password_hash  varchar(255),
  access_count   integer NOT NULL DEFAULT 0 CHECK (access_count >= 0),
  last_accessed_at timestamptz,
  created_by     uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  revoked_at     timestamptz
);

COMMENT ON TABLE share_links IS '报告二维码/H5 分享链接，仅保存 Token 哈希';

CREATE TABLE IF NOT EXISTS report_exports (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id    uuid NOT NULL REFERENCES assessment_reports(id) ON DELETE CASCADE,
  export_type  varchar(32) NOT NULL DEFAULT 'pdf'
               CHECK (export_type IN ('pdf', 'html', 'image', 'json')),
  file_id      uuid REFERENCES file_objects(id) ON DELETE SET NULL,
  status       varchar(32) NOT NULL DEFAULT 'queued'
               CHECK (status IN ('queued', 'generated', 'failed')),
  generated_by uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE report_exports IS '报告导出记录：PDF、HTML、图片、JSON';

CREATE TABLE IF NOT EXISTS report_access_logs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id     uuid NOT NULL REFERENCES assessment_reports(id) ON DELETE CASCADE,
  share_link_id uuid REFERENCES share_links(id) ON DELETE SET NULL,
  viewer_role   varchar(32) NOT NULL,
  viewer_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  ip_hash       varchar(128),
  user_agent    text,
  accessed_at   timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE report_access_logs IS '报告查看、扫码访问和下载行为日志';

CREATE TABLE IF NOT EXISTS audit_logs (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid REFERENCES organizations(id) ON DELETE SET NULL,
  user_id         uuid REFERENCES users(id) ON DELETE SET NULL,
  action          varchar(128) NOT NULL,
  resource_type   varchar(64) NOT NULL,
  resource_id     uuid,
  detail          jsonb NOT NULL DEFAULT '{}'::jsonb,
  ip_hash         varchar(128),
  user_agent      text,
  created_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE audit_logs IS '系统级审计日志：登录、查看、修改、审核、发布、导出、分享等';

-- ---------------------------------------------------------------------
-- 7. 触发器
-- ---------------------------------------------------------------------

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'organizations', 'classes', 'users', 'student_profiles', 'counselor_assignments',
    'consent_records', 'theory_sources', 'theory_concepts', 'asset_categories',
    'miniatures', 'assessment_sessions', 'terrain_states', 'sandplay_items',
    'self_reports', 'academic_transcripts', 'ai_prompt_templates', 'ai_analysis_jobs',
    'assessment_reports', 'report_sections', 'report_dimension_assessments',
    'risk_assessments', 'training_modules'
  ]
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_%I_updated_at ON %I', t, t);
    EXECUTE format('CREATE TRIGGER trg_%I_updated_at BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION set_updated_at()', t, t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------
-- 8. 索引
-- ---------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_users_org_role_status ON users (organization_id, role, status);
CREATE INDEX IF NOT EXISTS idx_student_profiles_class ON student_profiles (class_id);
CREATE INDEX IF NOT EXISTS idx_consent_student_status ON consent_records (student_id, status);
CREATE INDEX IF NOT EXISTS idx_miniatures_category_active ON miniatures (category_id, is_active);
CREATE INDEX IF NOT EXISTS idx_theory_concepts_source ON theory_concepts (source_id);
CREATE INDEX IF NOT EXISTS idx_sessions_student_created ON assessment_sessions (student_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_counselor_status ON assessment_sessions (counselor_id, status);
CREATE INDEX IF NOT EXISTS idx_snapshots_session_final ON sandplay_snapshots (session_id, is_final);
CREATE UNIQUE INDEX IF NOT EXISTS uq_one_final_snapshot_per_session ON sandplay_snapshots (session_id) WHERE is_final = true;
CREATE INDEX IF NOT EXISTS idx_items_session_final ON sandplay_items (session_id, is_final);
CREATE INDEX IF NOT EXISTS idx_items_grid_cell ON sandplay_items (grid_cell_id);
CREATE INDEX IF NOT EXISTS idx_events_session_seq ON process_events (session_id, seq_no);
CREATE INDEX IF NOT EXISTS idx_transcripts_session_status ON academic_transcripts (session_id, ocr_status);
CREATE INDEX IF NOT EXISTS idx_ai_jobs_session_status ON ai_analysis_jobs (session_id, status);
CREATE INDEX IF NOT EXISTS idx_reports_session_status ON assessment_reports (session_id, status);
CREATE INDEX IF NOT EXISTS idx_reports_status_published ON assessment_reports (status, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_report_level ON risk_assessments (report_id, level);
CREATE INDEX IF NOT EXISTS idx_share_report_status ON share_links (report_id, status);
CREATE INDEX IF NOT EXISTS idx_access_logs_report_time ON report_access_logs (report_id, accessed_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_org_resource ON audit_logs (organization_id, resource_type, resource_id, created_at DESC);

-- ---------------------------------------------------------------------
-- 9. 统计视图
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW v_student_report_summary AS
SELECT DISTINCT ON (s.student_id)
  s.student_id,
  sp.student_no,
  u.display_name AS student_name,
  s.organization_id,
  s.class_id,
  r.id AS report_id,
  r.report_no,
  r.status,
  r.version,
  r.published_at,
  r.updated_at
FROM assessment_sessions s
JOIN student_profiles sp ON sp.user_id = s.student_id
JOIN users u ON u.id = s.student_id
JOIN assessment_reports r ON r.session_id = s.id
ORDER BY s.student_id, r.published_at DESC NULLS LAST, r.version DESC;

COMMENT ON VIEW v_student_report_summary IS '学生最新报告摘要视图';

CREATE OR REPLACE VIEW v_risk_level_distribution AS
SELECT
  s.organization_id,
  ra.level,
  COUNT(*) AS student_count
FROM risk_assessments ra
JOIN assessment_reports r ON r.id = ra.report_id
JOIN assessment_sessions s ON s.id = r.session_id
WHERE r.status IN ('approved', 'published')
GROUP BY s.organization_id, ra.level;

COMMENT ON VIEW v_risk_level_distribution IS 'L1-L4 风险等级分布统计视图';

CREATE OR REPLACE VIEW v_top_miniatures AS
SELECT
  s.organization_id,
  m.id AS miniature_id,
  m.code,
  m.name,
  ac.name AS category_name,
  COUNT(*) AS usage_count
FROM sandplay_items si
JOIN assessment_sessions s ON s.id = si.session_id
JOIN miniatures m ON m.id = si.miniature_id
JOIN asset_categories ac ON ac.id = m.category_id
WHERE si.is_final = true
GROUP BY s.organization_id, m.id, m.code, m.name, ac.name
ORDER BY usage_count DESC;

COMMENT ON VIEW v_top_miniatures IS '高频沙具 Top 统计视图';

CREATE OR REPLACE VIEW v_grid_heatmap AS
SELECT
  s.organization_id,
  gc.code AS grid_cell_code,
  gc.name AS grid_cell_name,
  COUNT(*) AS item_count,
  COUNT(DISTINCT si.session_id) AS session_count
FROM sandplay_items si
JOIN assessment_sessions s ON s.id = si.session_id
JOIN grid_cells gc ON gc.id = si.grid_cell_id
WHERE si.is_final = true
GROUP BY s.organization_id, gc.code, gc.name;

COMMENT ON VIEW v_grid_heatmap IS '九宫格空间聚集热力统计视图';

CREATE OR REPLACE VIEW v_training_module_needs AS
SELECT
  s.organization_id,
  tm.code AS module_code,
  tm.name AS module_name,
  COUNT(DISTINCT rtr.report_id) AS report_count
FROM report_training_recommendations rtr
JOIN training_modules tm ON tm.id = rtr.module_id
JOIN assessment_reports r ON r.id = rtr.report_id
JOIN assessment_sessions s ON s.id = r.session_id
WHERE r.status IN ('approved', 'published')
GROUP BY s.organization_id, tm.code, tm.name;

COMMENT ON VIEW v_training_module_needs IS '六大训练模块需求分布统计视图';

CREATE OR REPLACE VIEW v_academic_subject_distribution AS
SELECT
  s.organization_id,
  ts.subject_code,
  ts.subject_name,
  ts.track,
  COUNT(*) AS sample_count,
  AVG(ts.score_rate) AS avg_score_rate,
  COUNT(*) FILTER (WHERE ts.level = 'excellent') AS excellent_count,
  COUNT(*) FILTER (WHERE ts.level IN ('pass', 'fail')) AS weak_count
FROM transcript_subjects ts
JOIN academic_transcripts at ON at.id = ts.transcript_id
JOIN assessment_sessions s ON s.id = at.session_id
WHERE at.ocr_status = 'confirmed'
GROUP BY s.organization_id, ts.subject_code, ts.subject_name, ts.track;

COMMENT ON VIEW v_academic_subject_distribution IS '学业科目优势与薄弱分布统计视图';

-- ---------------------------------------------------------------------
-- 10. 基础字典种子数据
-- ---------------------------------------------------------------------

INSERT INTO grid_cells (code, name, row_index, col_index, spatial_meaning, sort_order) VALUES
('top_left', '左上', 1, 1, '发展性观察区域：可记录过去经验、外部环境或关系投射线索，不作诊断。', 1),
('top_center', '中上', 1, 2, '发展性观察区域：可记录目标、期待或上方空间意象线索，不作诊断。', 2),
('top_right', '右上', 1, 3, '发展性观察区域：可记录未来方向、理想或外部关系线索，不作诊断。', 3),
('middle_left', '左中', 2, 1, '发展性观察区域：可记录现实支持、关系边界或行动线索，不作诊断。', 4),
('center', '正中', 2, 2, '发展性观察区域：可记录自我核心、安全感容器或整合线索，不作诊断。', 5),
('middle_right', '右中', 2, 3, '发展性观察区域：可记录外部互动、行动方向或目标指向线索，不作诊断。', 6),
('bottom_left', '左下', 3, 1, '发展性观察区域：可记录基础安全感、过去经验或潜意识情绪线索，不作诊断。', 7),
('bottom_center', '中下', 3, 2, '发展性观察区域：可记录基础支撑、家庭/学校现实或稳定感线索，不作诊断。', 8),
('bottom_right', '右下', 3, 3, '发展性观察区域：可记录行动、现实资源或未来转化线索，不作诊断。', 9)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  row_index = EXCLUDED.row_index,
  col_index = EXCLUDED.col_index,
  spatial_meaning = EXCLUDED.spatial_meaning,
  sort_order = EXCLUDED.sort_order;

INSERT INTO asset_categories (code, name, description, sort_order) VALUES
('person_role', '人物与角色原型', '家庭成员、师生、职业与防御角色、奇幻与原型人物。', 1),
('building_home', '建筑与居所', '学校、图书馆、房屋、城堡、桥梁、栅栏、岗哨、医院等空间容器。', 2),
('nature_plant', '自然山水与植物', '山水、树木、花草、岩石、岛屿等自然意象。', 3),
('animal_myth', '动物与神兽', '家养动物、森林动物、猛兽、飞鸟、海洋生物和中国传统神兽。', 4),
('vehicle_tool', '交通工具与现代器物', '车辆、船舶、飞机、火箭、交通标识和现代器物。', 5),
('study_life', '学习与生活道具', '书桌、黑板、书本、奖杯、时钟、钥匙、望远镜、游乐设施等。', 6),
('mystic_symbol', '神秘与象征符号', '太极、八卦、水晶球、许愿池、篝火、旗帜、迷宫等象征符号。', 7),
('food_abundance', '饮食与丰饶意象', '餐桌、蛋糕、水果、稻田、粮仓、水井等滋养与丰饶意象。', 8)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  sort_order = EXCLUDED.sort_order;

INSERT INTO report_section_templates (code, title, sort_order, counselor_only, schema_hint) VALUES
('overview', '一、整体结果与场景概览', 1, false, '{"required":["cluster_area","blank_area","category_stats","scene_imagery","nine_grid_analysis"]}'),
('imagery_analysis', '二、沙盘作品意象分析', 2, false, '{"required":["theme","symbolic_miniatures","hypothesis"]}'),
('six_dimensions', '三、六维方向判定与训练模块指向', 3, false, '{"dimension_count":6}'),
('academic_evaluation', '四、学业成绩与学业评价', 4, false, '{"required":["total_score","score_rate","strength_subjects","weak_subjects"]}'),
('risk_assessment', '五、风险研判·九维度分级预警', 5, true, '{"dimension_count":9,"levels":["L1","L2","L3","L4"]}'),
('interview_suggestions', '六、访谈建议', 6, false, '{"targets":["student","guardian","teacher"]}'),
('career_strengths', '七、职业发展优势与三方行动', 7, false, '{"actions":["teacher","guardian","student"]}'),
('training_modules', '八、学习能力训练模块方向建议', 8, false, '{"module_count":6}'),
('general_advice', '九、总体使用建议', 9, false, '{"disclaimer":true}')
ON CONFLICT (code) DO UPDATE SET
  title = EXCLUDED.title,
  sort_order = EXCLUDED.sort_order,
  counselor_only = EXCLUDED.counselor_only,
  schema_hint = EXCLUDED.schema_hint;

INSERT INTO evaluation_dimensions (code, name, theory_framework, description, sort_order) VALUES
('cognitive_diagnosis', '全学科认知诊断', '布鲁姆认知目标分类学、认知负荷理论', '识别理解记忆、应用分析、结构表达等认知能力发展状态。', 1),
('subject_selection', '文理选科适配', '加德纳多元智能理论', '结合学科表现与智能倾向，观察文理方向适配性。', 2),
('interest_potential', '兴趣特长与潜能', '自我决定理论、心流理论', '观察自主感、胜任感、兴趣表达与沉浸潜能。', 3),
('academic_planning', '升学与学业规划', '霍兰德 RIASEC、舒伯生涯发展理论', '观察目标感、生涯探索和学习规划能力。', 4),
('family_ecology', '家庭生态协同', '鲍恩家庭系统理论、韦纳归因理论', '观察家庭互动、情绪系统与学业状态之间的协同关系。', 5),
('motivation_rebuild', '综合动力重塑', '德韦克成长型思维理论', '观察学习动机、归因模式、胜任感重建和成长型思维。', 6)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  theory_framework = EXCLUDED.theory_framework,
  description = EXCLUDED.description,
  sort_order = EXCLUDED.sort_order;

INSERT INTO training_modules (code, name, target_abilities, training_logic, forms, sort_order) VALUES
('focus_flow', '模块一：专注力与沉浸训练（心流模块）', ARRAY['持续专注', '任务坚持', '沉浸体验'], '由短时专注过渡到长时沉浸，任务难度阶梯上升并即时反馈。', ARRAY['限时间关任务', '沉浸式情景任务', '专注打卡'], 1),
('logic_expression', '模块二：逻辑思维与结构化表达训练', ARRAY['因果推理', '结构化表达', '观察描述'], '把动手操作经验转化为语言逻辑，形成操作—表达双通道。', ARRAY['看图说话', '思维导图', '区域关系讲解'], 2),
('spatial_transfer', '模块三：空间认知与学习策略迁移训练', ARRAY['空间智能', '分类布局', '策略迁移'], '巩固空间认知优势，并迁移到学习策略与生活管理。', ARRAY['空间建构', '地图迷宫', '整理规划任务'], 3),
('interpersonal_emotion', '模块四：人际互动与情绪表达训练', ARRAY['人际理解', '情绪识别', '主动互动'], '由静态认知走向动态互动，补足情绪表达和人际理解。', ARRAY['角色扮演', '情绪卡片', '亲子共练'], 4),
('goal_planning', '模块五：目标管理与学业规划训练', ARRAY['目标分解', '计划执行', '自我管理'], '形成目标—计划—执行—复盘的完整闭环。', ARRAY['成绩复盘', '目标阶梯', '周计划打卡'], 5),
('family_collaboration', '模块六：家庭协同与亲子沟通训练', ARRAY['亲子连接', '非评判回应', '过程激励'], '家庭侧配合学生侧训练，形成闭环支持。', ARRAY['家长微课', '亲子共练', '沟通话术练习'], 6)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  target_abilities = EXCLUDED.target_abilities,
  training_logic = EXCLUDED.training_logic,
  forms = EXCLUDED.forms,
  sort_order = EXCLUDED.sort_order;

CREATE TABLE IF NOT EXISTS risk_dimensions (
  code varchar(64) PRIMARY KEY,
  name varchar(64) NOT NULL,
  sort_order integer NOT NULL,
  counselor_only boolean NOT NULL DEFAULT true CHECK (counselor_only = true)
);

COMMENT ON TABLE risk_dimensions IS '九维风险研判字典，仅咨询师可见';

INSERT INTO risk_dimensions (code, name, sort_order) VALUES
('depression', '抑郁', 1),
('anxiety', '焦虑', 2),
('academic_stress', '学习压力感', 3),
('learning_burnout', '学习倦怠', 4),
('obsession', '强迫', 5),
('paranoia', '偏执', 6),
('hostility', '敌对', 7),
('interpersonal_sensitivity', '人际关系敏感', 8),
('self_harm_risk', '自我伤害倾向', 9)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  sort_order = EXCLUDED.sort_order;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_risk_assessments_dimension_code'
  ) THEN
    ALTER TABLE risk_assessments
      ADD CONSTRAINT fk_risk_assessments_dimension_code
      FOREIGN KEY (dimension_code) REFERENCES risk_dimensions(code)
      ON UPDATE CASCADE ON DELETE RESTRICT;
  END IF;
END $$;

INSERT INTO tags (code, name, tag_type) VALUES
('boundary_defense', '边界防御', 'theme'),
('safety_container', '安全容器', 'theme'),
('self_healing', '自我治愈', 'theme'),
('family_relation', '家庭关系', 'theme'),
('school_learning', '学校学习', 'learning'),
('hero_archetype', '英雄原型', 'archetype'),
('wise_old_man', '智慧老人', 'archetype'),
('shadow', '阴影', 'archetype'),
('persona', '人格面具', 'archetype'),
('individuation', '自性化', 'archetype'),
('mountain_water', '山水意象', 'culture'),
('yin_yang', '阴阳意象', 'culture')
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  tag_type = EXCLUDED.tag_type;

-- 理论来源：本地书籍 + 权威在线核验源
INSERT INTO theory_sources (code, title, author, publisher, published_on, isbn, source_type, url, local_path, reliability_level, verified_at, notes) VALUES
('book_xiangting', '箱庭疗法', '张日昇', '人民教育出版社', '2006-05-01', '9787107192623', 'book', NULL, 'D:\AI\AI_SandBox\参考\箱庭疗法_张日昇.pdf', 'high', now(), '用户提供的本地扫描版，一级理论来源。'),
('book_psychoanalysis', '心理分析：理解与体验', '申荷永', '生活·读书·新知三联书店', '2004-07-01', '9787108021175', 'book', NULL, 'D:\AI\AI_SandBox\参考\心理分析：理解与体验.pdf', 'high', now(), '用户提供的本地扫描版，一级理论来源。'),
('book_jung', '荣格与分析心理学', '申荷永', '广东高等教育出版社', '2004-10-01', '9787536130722', 'book', NULL, 'D:\AI\AI_SandBox\参考\荣格与分析心理学.pdf', 'high', now(), '用户提供的本地扫描版，一级理论来源。'),
('src_pep_xiangting', '人民教育出版社《箱庭疗法》官方书目', '人民教育出版社', '人民教育出版社', NULL, '9787107192623', 'publisher_page', 'https://www.pep.com.cn/products/zhytu/xlxl/201509/t20150918_1247294.shtml', NULL, 'high', now(), '用于核验目录、出版信息与书摘。'),
('src_cas_xiangting_review', '中国科学院心理研究所《箱庭疗法》书评', '中国科学院心理研究所', '中国科学院心理研究所机构知识库', NULL, NULL, 'academic_review', 'https://ir.psych.ac.cn/bitstream/311026/3250/1/%E4%B8%80%E6%9C%AC%E4%BB%8B%E7%BB%8D%E5%BF%83%E7%90%86%E5%92%A8%E8%AF%A2%E4%B8%8E%E6%B2%BB%E7%96%97%E6%96%B9%E6%B3%95%E7%9A%84%E8%91%97%E4%BD%9C_%E7%AE%B1%E5%BA%AD%E7%96%97%E6%B3%95_.pdf', NULL, 'high', now(), '用于核验书籍结构、作者背景和理论定位。'),
('src_bnu_sandplay_course', '北京师范大学箱庭疗法课程资料', '北京师范大学心理学部', '北京师范大学心理学部', NULL, NULL, 'university_course', 'https://psych.bnu.edu.cn/xwzx/hdyg/bfd08f09b69043a4a13aa6063346b577.htm', NULL, 'high', now(), '用于核验自由与受保护空间、自我治愈力、非言语性等概念。'),
('src_scnu_publications', '华南师范大学心理应用研究中心学术著作列表', '华南师范大学', '华南师范大学心理应用研究中心', NULL, NULL, 'university_publication', 'https://mobile.scnu.edu.cn/psypc/11148/37', NULL, 'high', now(), '用于核验申荷永两本著作的出版信息。'),
('src_psyheart_psychoanalysis', '东方心理分析研究机构《心理分析：理解与体验》书目', '广东东方心理分析研究机构', '广东东方心理分析研究机构', NULL, NULL, 'institution_page', 'http://www.psyheart.net/list/13/235.htm', NULL, 'medium', now(), '用于核验《心理分析：理解与体验》目录与内容简介。'),
('src_nwupl_jung_catalog', '高校图书馆《荣格与分析心理学》馆藏目录', '西北政法大学图书馆', '西北政法大学图书馆', NULL, NULL, 'library_catalog', 'https://libm.nwupl.edu.cn/bookInfo_01h0024155.html', NULL, 'medium', now(), '用于核验《荣格与分析心理学》章节结构。')
ON CONFLICT (code) DO UPDATE SET
  title = EXCLUDED.title,
  author = EXCLUDED.author,
  publisher = EXCLUDED.publisher,
  published_on = EXCLUDED.published_on,
  isbn = EXCLUDED.isbn,
  source_type = EXCLUDED.source_type,
  url = EXCLUDED.url,
  local_path = EXCLUDED.local_path,
  reliability_level = EXCLUDED.reliability_level,
  verified_at = EXCLUDED.verified_at,
  notes = EXCLUDED.notes;

INSERT INTO theory_concepts (code, name_cn, name_en, source_id, chapter, definition_summary, application_scope, prohibited_boundary, prompt_allowed, metadata) VALUES
('free_protected_space', '自由与受保护的空间', 'Free and protected space', (SELECT id FROM theory_sources WHERE code='book_xiangting'), '箱庭疗法概论', '来访者在安全、受保护且不被评判的容器中自由表达无意识内容。', '用于解释沙盘容器、边界、安全感和制作过程氛围。', '不得据此推断临床疾病或家庭事实。', true, '{}'),
('mother_child_unity', '母子一体性', 'Mother-child unity', (SELECT id FROM theory_sources WHERE code='book_xiangting'), '箱庭疗法概论', '治疗者与来访者之间形成接纳、共情和安全感支持关系。', '用于描述咨询关系和容器功能。', '不得将沙盘元素直接解释为亲子关系诊断。', true, '{}'),
('self_healing', '自我治愈力', 'Self-healing', (SELECT id FROM theory_sources WHERE code='book_xiangting'), '箱庭疗法概论', '个体在自由受保护空间中通过象征表达激发生长与整合潜能。', '用于优势视角、成长建议和发展性支持。', '不得替代医疗、心理治疗或危机干预。', true, '{}'),
('process_record', '制作过程记录', 'Sandplay process recording', (SELECT id FROM theory_sources WHERE code='book_xiangting'), '箱庭的制作与记录', '制作动作、顺序、犹豫、修改、删除、抚平等过程信息具有观察价值。', '用于过程事件采集和行为轨迹分析。', '不得把单次动作机械解释为稳定人格特质。', true, '{}'),
('symbolic_configuration', '沙具象征与空间配置', 'Symbolic configuration', (SELECT id FROM theory_sources WHERE code='book_xiangting'), '箱庭疗法中的象征意义', '沙具、空间、疏密、动静和边界组合可形成象征性表达。', '用于沙具标签、九宫格分布和场景意象分析。', '象征解释必须标注为探索性假设。', true, '{}'),
('boundary_defense', '边界防御', 'Boundary defense', (SELECT id FROM theory_sources WHERE code='book_xiangting'), '箱庭作品的表现及分析', '围栏、围墙、岗哨、封闭空间等可提示边界、防御和安全感诉求。', '用于边界类沙具与空间聚类观察。', '不得直接等同于社交障碍或心理疾病。', true, '{}'),
('nine_grid_observation', '九宫格空间观察', 'Nine-grid spatial observation', (SELECT id FROM theory_sources WHERE code='book_xiangting'), '箱庭作品的表现及分析', '将沙盘划分为九宫格，观察区域密度、留白、中心与边缘关系。', '用于空间分布统计和报告概览。', '仅作发展性观察框架，不建立固定命运式解释。', true, '{}'),
('understanding_experience', '理解与体验', 'Understanding and experience', (SELECT id FROM theory_sources WHERE code='book_psychoanalysis'), '心理分析：理解与体验', '心理分析强调理解、体验、感受和意义生成，而非单纯评判。', '用于报告措辞、咨询师审核和访谈建议。', '禁止标签化、武断化、诊断化表达。', true, '{}'),
('heart_nature', '心性与感应', 'Heart-mind and resonance', (SELECT id FROM theory_sources WHERE code='book_psychoanalysis'), '心性与体验：东方的传统', '在中国文化语境中理解心、感应、意象与心理转化。', '用于山水、阴阳、家庭伦理和文化象征解释。', '不得神秘化或玄学化评估结论。', true, '{}'),
('three_levels_an', '安其不安、安其所安、安之若命', 'Three levels of psychological development', (SELECT id FROM theory_sources WHERE code='book_psychoanalysis'), '灵性与创造', '心理分析可从缓解不安、心理教育到自性发展三个层面发挥作用。', '用于总体建议和成长型支持路径。', '不得宣称一次性测评可完成自性发展判断。', true, '{}'),
('image_embodiment', '意象体现', 'Image embodiment', (SELECT id FROM theory_sources WHERE code='book_psychoanalysis'), '心理分析方法与技术', '意象承载情绪和潜意识内容，可通过体验与表达获得理解。', '用于沙盘场景意象、文化象征和情绪流动描述。', '不得将意象解释写成确定事实。', true, '{}'),
('nonjudgmental_ethics', '非评判性伦理', 'Non-judgmental ethics', (SELECT id FROM theory_sources WHERE code='book_psychoanalysis'), '心理分析中的伦理', '以善心、诚信、关爱和尊重为边界，避免评判与标签化。', '用于报告措辞和审核规则。', '禁止病理化、羞辱性、歧视性表达。', true, '{}'),
('collective_unconscious', '集体无意识', 'Collective unconscious', (SELECT id FROM theory_sources WHERE code='book_jung'), '分析心理学的基本理论', '人类心灵中存在超越个人经验的深层结构与共同象征。', '用于解释跨文化原型和象征素材。', '不得把象征解释为不可改变的命运。', true, '{}'),
('archetype', '原型', 'Archetype', (SELECT id FROM theory_sources WHERE code='book_jung'), '原型的理论', '原型是集体无意识中的普遍心理结构，可通过意象显现。', '用于人物、神兽、英雄、智慧老人等沙具解释。', '不得机械套用原型标签。', true, '{}'),
('persona', '人格面具', 'Persona', (SELECT id FROM theory_sources WHERE code='book_jung'), '原型的意象', '个体面向外部社会角色与期待时呈现的适应性面具。', '用于职业角色、防御角色、制服人物等观察。', '不得推断真实人格或道德评价。', true, '{}'),
('shadow', '阴影', 'Shadow', (SELECT id FROM theory_sources WHERE code='book_jung'), '原型的意象', '阴影代表个体未整合、被压抑或不愿面对的心理内容。', '用于猛兽、黑暗、冲突、攻击性和防御场景观察。', '不得将阴影等同于危险或病理。', true, '{}'),
('anima', '阿尼玛', 'Anima', (SELECT id FROM theory_sources WHERE code='book_jung'), '原型的意象', '荣格理论中男性心理中的女性性原型意象。', '仅用于理论字典和专业语境。', '不对学生作性别化刻板解释。', false, '{}'),
('animus', '阿尼姆斯', 'Animus', (SELECT id FROM theory_sources WHERE code='book_jung'), '原型的意象', '荣格理论中女性心理中的男性性原型意象。', '仅用于理论字典和专业语境。', '不对学生作性别化刻板解释。', false, '{}'),
('wise_old_man', '智慧老人', 'Wise old man', (SELECT id FROM theory_sources WHERE code='book_jung'), '原型的意象', '象征智慧、引导、内在资源和转化潜能的原型意象。', '用于教师、长者、灯塔、向导等支持性意象观察。', '不得神话个体或暗示权威依赖。', true, '{}'),
('individuation', '自性化过程', 'Individuation', (SELECT id FROM theory_sources WHERE code='book_jung'), '自性化过程', '个体整合意识与无意识、发展完整自我的过程。', '用于长期成长建议，不用于单次测评定性。', '不得用单次沙盘判断自性化阶段。', true, '{}'),
('symbolic_analysis', '象征性分析', 'Symbolic analysis', (SELECT id FROM theory_sources WHERE code='book_jung'), '分析心理学的主要方法', '通过象征、联想和意象理解心理内容。', '用于沙具象征解释和 LLM Prompt 约束。', '必须保留假设性和访谈确认要求。', true, '{}'),
('active_imagination', '积极想象', 'Active imagination', (SELECT id FROM theory_sources WHERE code='book_jung'), '分析心理学的主要方法', '通过主动接触意象促进意识与无意识之间的对话。', '用于访谈建议和后续表达性活动设计。', '不得替代专业治疗过程。', true, '{}')
ON CONFLICT (code) DO UPDATE SET
  name_cn = EXCLUDED.name_cn,
  name_en = EXCLUDED.name_en,
  source_id = EXCLUDED.source_id,
  chapter = EXCLUDED.chapter,
  definition_summary = EXCLUDED.definition_summary,
  application_scope = EXCLUDED.application_scope,
  prohibited_boundary = EXCLUDED.prohibited_boundary,
  prompt_allowed = EXCLUDED.prompt_allowed,
  metadata = EXCLUDED.metadata;

INSERT INTO ai_prompt_templates (code, version, name, system_prompt, theory_source_ids, report_schema, status) VALUES
(
  'sandplay_assessment',
  'v1.0',
  '心理沙盘与学习动力发展性评估专家',
  '你是基于张日昇《箱庭疗法》、申荷永《心理分析：理解与体验》《荣格与分析心理学》的发展与教育心理评估专家。所有输出必须为发展性、非临床诊断、可访谈确认的探索性假设，并严格输出约定的九段 JSON。',
  ARRAY[
    (SELECT id FROM theory_sources WHERE code='book_xiangting'),
    (SELECT id FROM theory_sources WHERE code='book_psychoanalysis'),
    (SELECT id FROM theory_sources WHERE code='book_jung')
  ],
  '{"top_level":["overview","imagery_analysis","six_dimensions","academic_evaluation","risk_assessment","interview_suggestions","career_strengths","training_modules","general_advice"],"risk_counselor_only":true}',
  'active'
)
ON CONFLICT (code, version) DO UPDATE SET
  name = EXCLUDED.name,
  system_prompt = EXCLUDED.system_prompt,
  theory_source_ids = EXCLUDED.theory_source_ids,
  report_schema = EXCLUDED.report_schema,
  status = EXCLUDED.status;

COMMIT;

-- =====================================================================
-- 文件结束
-- =====================================================================
