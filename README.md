# SandTable · 心理沙盘 3D 工作台

一个面向学校心理老师与咨询师的 3D 心理沙盘工作台：在浏览器中摆放沙具、塑形沙面、记录描述，提交后生成九章节发展性评估报告，并支持咨询师完整版与家长/学生脱敏版分享。

## 功能

- Three.js 3D 沙盘：堆沙、挖沙、挖水、抚平、旋转与缩放，导出高清沙盘图
- 500 件沙具库：8 个器物分类 + 81 个子类 + 5 个临床主题标签，双轴 AND 组合筛选
- 每件沙具统一 13 个字段：子类、资产组、具体释义、支持性假设、替代性假设、访谈核验问题、风险层级与空间角色；236 件带主题标签，264 件保持中性
- 收尾流程：选择代表沙具、填写沙盘描述与可选教师观察，再提交报告
- 九章节报告：六维分析、九维风险、访谈建议、生涯优势、训练模块
- 认知维度证据门控：有自述/成绩/教师观察时不直接由空间分布推断学科能力；缺证时保留跨学科类比并标注“理论假说·待核实”
- 管理后台：评估统计、审核队列、报告查看与分享二维码
- 双版本报告：咨询师完整版与家长/学生脱敏版；风险章节仅咨询师可见

## 目录

```
sandplay_workbench_react.html   前端 3D 工作台（单文件 React + Three.js）
report_viewer_v2.html           报告精排 H5 / A4 打印页
report_viewer.html              旧入口，自动跳转到 v2
admin_dashboard.html            管理后台
backend/                        FastAPI + SQLite 后端
assets/sandplay_miniatures_500.json   500 件沙具主数据（schema 1.1）
assets/sandplay_miniatures_500.csv    500 行字段审计表
scripts/unify_sandplay_taxonomy.py    旧 400 件子类/主题/双假设补齐与统计
scripts/build_sandplay_library.py     运行时资产库构建与 schema 校验
assets/generated/sandplay_library.js  运行时沙具库（内嵌 WebP）
assets/generated/transparent/         600 组透明底 PNG / WebP 素材
contracts/                      API 与数据库契约
生成脚本（根目录 _*.py）        资产生成、修复与报告排版脚本
```

## 本地启动

### 1. 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# 编辑 .env，填入 MULTIMODAL_API_KEY 等配置
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查：`http://127.0.0.1:8000/api/v1/health`

### 2. 前端静态服务

```powershell
cd D:\AI\AI_SandBox
python -m http.server 8765
```

打开：`http://127.0.0.1:8765/sandplay_workbench_react.html`

也可以直接双击 `sandplay_workbench_react.html`，前端默认请求 `http://127.0.0.1:8000/api/v1`。

## 沙具素材

仓库包含：

- `assets/generated/transparent/`：600 组透明底沙具素材，PNG 与 WebP 各一份，约 116 MB
- `assets/generated/sandplay_library.js`：运行时库，500 件沙具，含子类、主题、风险层级、空间角色与双假设；图片以 WebP data URI 内嵌
- `assets/generated/previews/`：五个临床主题预览图
- `assets/sandplay_miniatures_500.json`：器物分类、子类、临床主题、双假设与沙具元数据
- `assets/sandplay_miniatures_500.csv`：500 行字段审计表，可按批次、主题、风险层级、子类筛选
- `沙具JSON字段审计与优化说明_20261120.md`：旧 400 件与新增 100 件的字段对比及改造说明

未提交 `assets/generated/white/`：这是生成阶段的白底原图，约 1.5 GB，运行时不需要；如需重新生成或重新抠图，请保留在本地。

## 隐私

仓库不包含：

- `.env` 与任何 API Key
- `backend/data/sandplay.db`
- `backend/data/uploads/` 中的真实沙盘图片、成绩单与自述
- 本地日志

提交前请确认 `.env` 与 `backend/data/` 仍被 `.gitignore` 忽略。

## 说明

报告为发展性心理评估参考，不是临床诊断；风险研判与访谈建议需由专业咨询师结合面谈、量表与教师/家长观察核实。
