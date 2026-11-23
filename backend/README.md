# 心理沙盘发展性评估后端

FastAPI + SQLAlchemy 2.x + SQLite / PostgreSQL，用于接收 3D 沙盘作品，生成严格九章节报告，并提供家长/学生端分享二维码。

## 启动

```powershell
cd D:\AI\AI_SandBox\backend
python -m pip install -r requirements.txt
Copy-Item .env.example .env   # 首次使用；按需填写多模态密钥
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- 健康检查：`http://127.0.0.1:8000/api/v1/health`
- Swagger：`http://127.0.0.1:8000/docs`
- 默认数据库：`data/sandplay.db`
- 上传文件：`data/uploads/<assessment_id>/`
- 分享页：`http://127.0.0.1:8000/share/<token>`（303 跳转到 `/report-viewer?share_token=<token>`）
- 报告精排页：`http://127.0.0.1:8000/report-viewer?report_id=<id>&mode=counselor`

## 前端接入

前端文件为 `D:\AI\AI_SandBox\sandplay_workbench_react.html`。前端必须与后端同源部署，默认请求：

```
http://127.0.0.1:8000/api/v1
```

前端不再读取 `localStorage.sandplay_report_api` 覆盖 API 地址，避免会话令牌被带到非预期域名。若后端换地址，请直接修改同源反向代理。

“结束制作”后的流程：

1. 选择一件最能代表自己的沙具；
2. 写一段不少于 10 字的沙盘描述，可给沙盘起名并可选填自述与学生信息；
3. 提交沙盘图、沙具、九宫格 JSON、地形高度图、代表沙具与文字；
4. 报告生成后自动打开导出弹窗，可复制/下载九章 JSON、下载高清 PNG、打开“精排报告”、生成分享二维码；精排页支持咨询师完整版 / 家长学生脱敏版切换与 html2pdf A4 导出。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/health` | 健康检查 |
| POST | `/api/v1/assessments` | 创建评估，`multipart/form-data` |
| GET | `/api/v1/assessments/{id}` | 学生查看本人提交状态 |
| GET | `/api/v1/reports/{id}` | 咨询师完整九章报告，需 `Authorization: Bearer <session-token>` |
| POST | `/api/v1/reports/{id}/share` | 生成 30 天有效的分享 token、分享 URL、二维码 data URI |
| GET | `/api/v1/share/access` | 家长/学生端 JSON，需请求头 `X-Share-Token` |
| GET | `/share/{token}` | 旧二维码兼容入口，303 跳转到 fragment 形式 |
| GET | `/report-viewer` | 报告精排 H5 / A4 打印页，支持 `report_id`、`mode` 或 `#share_token` |
| DELETE | `/api/v1/shares/{token}` | 撤回分享链接，需咨询师 / 超级管理员会话 |

创建评估的 multipart 字段：

- `payload`：JSON 字符串，核心字段 `student`、`items`、`grid_distribution`、`heightmap`、`representative_item_id`、`representative_item_name`、`sand_name`、`sandplay_description`、`self_narrative`、`consent`；
- `sandplay_image`：必传，前端导出的 PNG；
- `transcript_image`：可选，成绩单图片。
- 服务端会忽略学生伪造的 `teacher_observation` 与 `_` 开头的内部字段。

也兼容 `sandplay_image_base64` / `transcript_image_base64` 表单字段。


## 九章结构

固定键与章节：

1. `chapter_1_overview` 整体结果与场景概览
2. `chapter_2_imagery` 沙盘作品意象分析
3. `chapter_3_six_dimensions` 六维方向判定与训练模块指向
4. `chapter_4_academic` 学业成绩与学业评价
5. `chapter_5_risk` 风险研判（九维度分级预警·仅咨询师可见）
6. `chapter_6_interview` 访谈建议
7. `chapter_7_career` 职业发展优势
8. `chapter_8_training_modules` 学习能力训练模块方向建议
9. `chapter_9_general_advice` 总体使用建议

结构校验：

- 六维必须 6 项：全学科认知诊断、文理选科适配、兴趣特长与潜能、升学与学业规划、家庭生态协同、综合动力重塑；
- 风险必须 9 项：抑郁、焦虑、学习压力感、学习倦怠、强迫、偏执、敌对、人际关系敏感、自我伤害倾向；
- 训练模块必须 6 项，顺序固定；
- 自我像为独立字段，不要求出现在 `items[].id`，只进入第二章意象假设与访谈，不直接参与九维风险分级；
- 风险硬门控：单件非死亡类高危沙具 → `L3_ORANGE`；死亡类符号、两件及以上高危沙具、明确的负向文本或掩埋/破坏过程 → `L4_RED`；
- 视觉高危物体单独筛查：单件枪械/刀具/血/伤/排泄物等 `high` 物体 → L3；尸体/悬吊/两件及以上 → L4；军事/警察/博物馆/玩具陈列或厕所/医疗语境最多 `watch`；
- 不满足时多模态报告会失败降级（`ALLOW_DEMO_REPORT=false` 时直接报错）。

理论依据使用张日昇《箱庭疗法》、申荷永《心理分析：理解与体验》、申荷永《荣格与分析心理学》的概念转述与书目署名，不伪造原文引语或页码。认知维度有自述、成绩或教师观察时，不以箱庭空间分布直接推断学科能力；缺少这些材料时，跨域理论类比必须标为“理论假说·待核实”。

## 多模态配置

任何 OpenAI 兼容 `/chat/completions` 服务均可：

```env
MULTIMODAL_API_KEY=...
MULTIMODAL_BASE_URL=https://api.openai.com/v1
MULTIMODAL_MODEL=gpt-4o-mini
MULTIMODAL_TIMEOUT_SECONDS=180
```

- 未配置密钥时自动生成本地演示报告，响应里 `report_engine="demo"`；
- 配置密钥后，成绩单图片会作为第二张图片传入，让模型逐科读取分数；
- 模型输出必须通过九章节 Pydantic 校验，失败时按 `ALLOW_DEMO_REPORT` 决定降级或报错。

## 分享端隐私

`app/utils.py` 的 `public_copy()` 在服务端序列化层执行：

- 删除 `chapter_5_risk`；
- 删除 `risk_level`、`risk_summary`、`counselor_*` 等咨询师字段；
- 删除 `nine_grid_distribution`、`grid_distribution`、`heightmap` 原始后台数据；
- 将“九宫格”“宫格”等算法词替换为“画面分区”“区域”；
- HTML 与 JSON 两个公开接口都使用同一份脱敏结果，不依赖前端隐藏。

## 切换 PostgreSQL

```env
DATABASE_URL=postgresql+psycopg://sandplay:password@127.0.0.1:5432/sandplay
```

表结构由 SQLAlchemy 在启动时自动创建。生产环境建议改用 Alembic 管理迁移，并替换默认咨询师令牌、限制 `CORS_ORIGINS`、把 `PUBLIC_BASE_URL` 改成手机可访问的局域网或公网地址。

## 当前联调结果

- 前端真实提交 3 件沙具、9 格分布、161×101 高度图（16,261 个数值）、代表沙具“爷爷”、描述、自述、学生信息和成绩单图片；
- 创建评估返回 200，报告含 9 章、六维 6 项、风险 9 项、训练模块 6 项；
- 分享二维码生成成功；
- 公开 JSON / HTML 均不含 `chapter_5_risk`，也不含“风险研判”“九维度”；
- 未带咨询师令牌访问完整报告返回 401。
