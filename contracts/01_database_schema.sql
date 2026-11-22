-- SandTable / 心理沙盘项目 数据库结构
-- 与 backend/app/models.py 当前实现一致；默认运行在 SQLite（backend/data/sandplay.db）。
-- SQLAlchemy 同时兼容 PostgreSQL；本文件以 PostgreSQL 语法书写标准结构。
-- 说明：本项目不使用会话表（sessions）、分析任务表（analysis_jobs）或历史多表拆分模型。
-- 旧库升级由 backend/app/db.py::_migrate_legacy_schema 以 ALTER TABLE ADD COLUMN 增量补列，不删历史数据。

CREATE TABLE assessments (
    id VARCHAR(36) PRIMARY KEY,
    student_no VARCHAR(64) NOT NULL,
    student_name VARCHAR(80) NOT NULL,
    grade_level VARCHAR(40) NOT NULL,
    gender VARCHAR(20) NOT NULL,
    representative_item_id VARCHAR(120) NOT NULL,
    representative_item_name VARCHAR(120) NOT NULL,
    sandplay_description TEXT NOT NULL,
    self_narrative TEXT,
    consent BOOLEAN NOT NULL,
    sandplay_image_path TEXT NOT NULL,
    transcript_image_path TEXT,
    input_payload TEXT NOT NULL,
    heightmap_json TEXT NOT NULL,
    grid_distribution_json TEXT NOT NULL,
    items_json TEXT NOT NULL,
    report_json TEXT,
    report_engine VARCHAR(40) NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    -- 学生档案（2026-11 增量列）
    school_name VARCHAR(120) DEFAULT '',
    class_name VARCHAR(80) DEFAULT '',
    seat_no VARCHAR(40) DEFAULT '',
    contact_phone VARCHAR(80) DEFAULT '',
    academic_scores_json TEXT DEFAULT '{}',
    -- 报告修订版本号：每次“审核通过并合并人工修订” +1
    report_revision INTEGER DEFAULT 0
);

CREATE INDEX ix_assessments_student_no ON assessments (student_no);
CREATE INDEX ix_assessments_status ON assessments (status);

CREATE TABLE report_reviews (
    assessment_id VARCHAR(36) PRIMARY KEY REFERENCES assessments (id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    note TEXT NOT NULL DEFAULT '',
    reviewer_id VARCHAR(36),
    updated_at TIMESTAMP NOT NULL,
    -- AI 原稿快照，人工修订不会覆盖，便于追溯与还原
    ai_report_json TEXT,
    -- 咨询师草稿（仅允许改写第二章 / 第六章 / 第九章）
    draft_report_json TEXT,
    draft_note TEXT DEFAULT '',
    draft_updated_at TIMESTAMP,
    review_applied_at TIMESTAMP
);

CREATE INDEX ix_report_reviews_status ON report_reviews (status);

CREATE TABLE share_links (
    token VARCHAR(96) PRIMARY KEY,
    assessment_id VARCHAR(36) NOT NULL REFERENCES assessments (id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    access_count INTEGER NOT NULL DEFAULT 0,
    last_accessed_at TIMESTAMP
);

CREATE INDEX ix_share_links_assessment_id ON share_links (assessment_id);

CREATE TABLE admin_users (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    account VARCHAR(64) NOT NULL UNIQUE,
    role_key VARCHAR(32) NOT NULL,
    department VARCHAR(80) NOT NULL,
    grade_level VARCHAR(40) NOT NULL,
    class_name VARCHAR(40) NOT NULL,
    student_no VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_admin_users_role_key ON admin_users (role_key);
CREATE INDEX ix_admin_users_status ON admin_users (status);

-- 字段语义备注
-- assessments.status        : analyzing / completed / failed
-- assessments.report_engine : 报告生成引擎标识；值为 demo 时报告正文带 demo_report=true
-- assessments.input_payload : 工作台完整提交的 JSON，含 spatial_relations / process_snapshots 等过程数据
-- report_reviews.status     : pending / changes / rejected / approved
-- 角色权限说明（当前实现）：服务端只校验统一请求头 X-Counselor-Token；
-- admin_users.role_key 用于后台展示与前端角色视图，不参与服务端分权校验。
