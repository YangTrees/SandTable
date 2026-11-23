# SandTable · 心理沙盘 3D 工作台

面向学校心理测评场景的 3D 心理沙盘系统：学生使用学校发放的账号进入工作台，在浏览器中摆放沙具、塑造地形、记录制作过程与描述，完成后提交给心理老师；教职员工在管理后台审核、修订并生成家长 / 学生分享页。

## 功能

- Three.js 3D 沙盘：固定 4:3（1200 × 900）沙箱，支持堆沙、挖沙、挖水、抚平、笔刷直径与力度、撤销 / 重做、沙具水平镜像
- 500 件沙具库：按器物分类与子类检索，支持搜索、分类筛选和场景内微调
- 工作台档案：学生登录后只读显示姓名、学号、学部 / 年级 / 班级；身份以账号为准，学生不能自行改档案
- 制作过程记录：实时计时、过程快照（最多 6 张）、地形操作计数、空间关系、九宫格分布与留白估算
- 收尾流程：选择代表沙具，填写沙盘描述、给沙盘起名与可选补充；完成后提交给心理老师，学生端只显示提交回执与脱敏简略报告
- 九章节报告：整体概览、意象假设、六维方向、学业表现、风险研判、访谈建议、生涯优势、训练模块、总体建议
- 认知维度证据门控：有自述 / 成绩 / 教师观察时不直接由空间分布推断学科能力；缺证时标注“理论假说·待核实”
- 管理后台：报告范围筛选、评估统计、审核队列、AI 正文修订草稿、审核通过后生成分享二维码
- 双版本报告：咨询师完整版与家长 / 学生脱敏版；风险章节仅咨询师可见，班主任账号只能查看班级汇总，不能读取个体报告
- 入口隔离：`/admin` 只接受教职员工账号，`/workbench` 只接受学生账号；学生账号只能由超级管理员创建
- 分享链接默认 30 天有效，令牌放在 URL fragment 中，通过请求头访问分享接口，避免进入访问日志
- Demo 报告显式标识，默认关闭（`ALLOW_DEMO_REPORT=false`）

## 技术结构

- 前端：单文件 HTML，React UMD + Three.js 渲染，无构建步骤；前端依赖已本地化到 `assets/vendor/`
- 后端：FastAPI + SQLAlchemy，开发环境默认 SQLite（`backend/data/sandplay.db`）
- 鉴权：后台与工作台分别使用独立会话；`/api/v1/admin/*` 拒绝学生账号，`/api/v1/workbench/*` 只接受学生账号
- 会话令牌存于 `sessionStorage`，请求使用 `Authorization: Bearer`；服务令牌默认关闭，且没有内置默认值
- 数据库表：`assessments / report_reviews / share_links / admin_users / admin_sessions`
- 报告存储：评估正文在 `assessments.report_json`，AI 原稿与审核草稿在 `report_reviews`

## 目录

```
sandplay_workbench_react.html   前端 3D 工作台（单文件 React + Three.js）
report_viewer_v2.html           报告精排 H5 / A4 打印页
report_viewer.html              旧版报告页，保留但不再由后端提供入口
admin_dashboard.html            管理后台
backend/app/                    FastAPI 应用、数据模型、报告引擎
backend/data/                   本地 SQLite 与上传文件（已忽略）
assets/sandplay_miniatures_500.json   500 件沙具主数据
assets/sandplay_miniatures_500.csv    500 行字段审计表
assets/generated/sandplay_library.js  运行时沙具库（内嵌 WebP）
assets/generated/transparent/         透明底 PNG / WebP 素材
assets/vendor/                     本地化前端依赖（ECharts / React / Three.js / html2pdf / Tailwind）
contracts/                      API 与数据库契约（需与当前实现持续核对）
```

## 本地启动

### 1. 后端

```powershell
cd D:\AI\AI_SandBox\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# 编辑 .env，填入 MULTIMODAL_API_KEY 等配置
# 首次空库启动必须设置 ADMIN_INITIAL_PASSWORD，用于初始化首位超级管理员
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查：`http://127.0.0.1:8000/api/v1/health`

首次启动会在 `backend/data/sandplay.db` 建表，并自动为历史库补齐新增列。

### 2. 前端入口

前端由 FastAPI 同源提供，不需要另起静态服务器：

- 学生测评入口：`http://127.0.0.1:8000/workbench`
- 教职员工控制台：`http://127.0.0.1:8000/admin`
- 操作手册：`http://127.0.0.1:8000/manual/`
- 报告查看器：从管理后台打开，不再需要单独的 `report_viewer.html`

## 公网发布

公网部署至少需要完成以下配置，详细检查清单见 `docs/公网发布安全与合规审核_20261123.md`：

1. `APP_ENV=production`
2. `PUBLIC_BASE_URL` 使用 HTTPS 正式域名
3. `CORS_ORIGINS` 只填写正式前端域名，禁止 `*`
4. `ENABLE_API_DOCS=false`
5. `ENABLE_MANUAL=false`，不要将内部操作手册与后台截图暴露到公网
6. `ENABLE_SERVICE_TOKEN=false`，并清空 `COUNSELOR_TOKEN`
7. `SEED_DEMO_USERS=false`，不要复制本地演示数据库
8. 配置独立强随机 `MEDIA_SIGNING_SECRET`；沙盘图与成绩单图片只通过短期签名 URL 提供，不能公开枚举 `/media`
9. 使用 PostgreSQL、持久化上传目录或对象存储，并配置定时备份
10. 反向代理启用 HTTPS、WAF / IP 限流、访问日志脱敏和进程守护
11. 首次初始化后移除 `ADMIN_INITIAL_PASSWORD`
12. 使用真实浏览器完成学生登录、提交、后台审核、报告查看与分享链接回归

## 主要接口

- `POST /api/v1/workbench/login`：学生登录
- `GET /api/v1/workbench/me`：学生当前会话
- `POST /api/v1/workbench/logout`：学生退出
- `POST /api/v1/assessments`：学生提交沙盘作品，只返回提交回执
- `GET /api/v1/assessments/{id}/status`：学生查看本人提交状态与脱敏简略报告
- `GET /api/v1/reports/{id}`：咨询师 / 超级管理员读取完整报告
- `POST /api/v1/reports/{id}/share`：生成 30 天有效的分享链接
- `GET /api/v1/share/access`：凭 `X-Share-Token` 请求头读取脱敏分享报告
- `POST /api/v1/admin/login`：教职员工登录
- `GET /api/v1/admin/me`：教职员工当前会话
- `POST /api/v1/admin/logout`：教职员工退出
- `GET /api/v1/admin/bootstrap`：后台初始化数据
- `GET /api/v1/admin/reports`：报告列表，支持 `school / class_name / grade / date_from / date_to / status / q`
- `GET /api/v1/admin/stats`：统计，支持同一组范围筛选
- `GET /api/v1/admin/reports/{id}/review-context`：AI 原稿、有效报告、草稿与预览
- `PUT /api/v1/admin/reports/{id}/review-draft`：保存第二、六、九章修订草稿
- `POST /api/v1/admin/reports/{id}/review`：审核通过 / 退回修订；通过时合并草稿并保留 AI 原稿

详见 `contracts/02_api_contract.md`，其中旧鉴权口径需以本文和代码为准。


## 沙具素材

- `assets/generated/transparent/`：透明底沙具素材，PNG 与 WebP 各一份
- `assets/generated/sandplay_library.js`：运行时库，图片以 WebP data URI 内嵌
- `assets/sandplay_miniatures_500.json`：沙具分类、子类、释义、支持性 / 替代性假设、访谈核验问题、风险层级与空间角色
- `assets/sandplay_miniatures_500.csv`：500 行字段审计表

未提交 `assets/generated/white/`：生成阶段的白底原图体积较大，运行时不需要，保留在本地用于重新抠图。

## 隐私

仓库不包含：

- `.env` 与任何 API Key
- `backend/data/sandplay.db`
- `backend/data/uploads/` 中的真实沙盘图片、成绩单与自述
- 本地日志

提交前请确认 `.env` 与 `backend/data/` 仍被 `.gitignore` 忽略。

## 说明

报告为发展性心理评估参考，不是临床诊断；风险研判与访谈建议需由专业咨询师结合面谈、量表与教师 / 家长观察核实。
