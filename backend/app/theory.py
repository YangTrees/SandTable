from __future__ import annotations

# 三本理论书的分析透镜。这里使用概念转述，不伪造原文引语或页码。
THEORY_EVIDENCE = [
    {
        "source": "张日昇《箱庭疗法》",
        "principle": "箱庭以沙、沙具和箱庭空间承载来访者的象征表达；理解时应同时关注作品整体、空间布局、沙具之间的关系与创作过程，不宜把单一沙具机械对应为固定结论。",
        "used_in": ["chapter_1_overview", "chapter_2_imagery", "chapter_5_risk", "chapter_6_interview", "chapter_9_general_advice"],
    },
    {
        "source": "申荷永《心理分析：理解与体验》",
        "principle": "心理分析以象征、意象、自由联想和体验性理解为路径，在咨询关系与生活情境中理解无意识表达；评估应保持探索性，避免把假设当作诊断。",
        "used_in": ["chapter_2_imagery", "chapter_6_interview", "chapter_9_general_advice"],
    },
    {
        "source": "申荷永《荣格与分析心理学》",
        "principle": "荣格分析心理学重视情结、原型与象征，个体化过程强调把无意识内容纳入意识并承担成长责任；阴影、投射等概念可用于提出假设，但不能替代临床访谈与专业判断。",
        "used_in": ["chapter_2_imagery", "chapter_5_risk", "chapter_6_interview"],
    },
]

RISK_DIMENSIONS = [
    ("depression", "抑郁"),
    ("anxiety", "焦虑"),
    ("learning_pressure", "学习压力感"),
    ("learning_burnout", "学习倦怠"),
    ("obsession", "强迫"),
    ("paranoia", "偏执"),
    ("hostility", "敌对"),
    ("interpersonal_sensitivity", "人际关系敏感"),
    ("self_harm", "自我伤害倾向"),
]

SIX_DIMENSIONS = [
    ("cognitive", "全学科认知诊断"),
    ("subject_choice", "文理选科适配"),
    ("interest_potential", "兴趣特长与潜能"),
    ("academic_planning", "升学与学业规划"),
    ("family_ecology", "家庭生态协同"),
    ("motivation_rebuild", "综合动力重塑"),
]

SIX_DIMENSION_THEORIES = {
    "全学科认知诊断": "认知负荷理论（Sweller, 1988）+ 元认知调节（Flavell, 1979）",
    "文理选科适配": "期望-价值理论（Eccles & Wigfield, 2002）+ 自我决定理论（Deci & Ryan, 1985）",
    "兴趣特长与潜能": "自我决定理论（Deci & Ryan, 1985）+ 心流理论（Csikszentmihalyi, 1990）",
    "升学与学业规划": "目标设定理论（Locke & Latham, 1990）+ 生涯建构理论（Savickas, 2005）",
    "家庭生态协同": "家庭系统理论（Bowen, 1978）+ 依恋理论（Bowlby, 1969）",
    "综合动力重塑": "自我决定理论（Deci & Ryan, 1985）+ 成长型思维（Dweck, 2006）",
}

RISK_INSTRUMENTS = {
    "depression": "PHQ-9 / CDI（儿童抑郁量表）",
    "anxiety": "GAD-7 / MHT（心理健康诊断测验）",
    "learning_pressure": "中学生学习压力问卷 / MHT 学习焦虑分量表",
    "learning_burnout": "青少年学习倦怠量表",
    "obsession": "CY-BOCS / SCL-90 强迫因子",
    "paranoia": "SCL-90 偏执因子",
    "hostility": "SCL-90 敌对因子 / 攻击性问卷",
    "interpersonal_sensitivity": "SCL-90 人际关系敏感因子",
    "self_harm": "C-SSRS（哥伦比亚自杀严重程度评定量表）+ 必须由专业人员面对面安全核查",
}

TRAINING_MODULES = [
    ("module_1_focus", "模块一：专注力与沉浸训练（心流模块）"),
    ("module_2_logic", "模块二：逻辑思维与结构化表达训练"),
    ("module_3_spatial", "模块三：空间认知与学习策略迁移训练"),
    ("module_4_interpersonal", "模块四：人际互动与情绪表达训练"),
    ("module_5_goals", "模块五：目标管理与学业规划训练"),
    ("module_6_family", "模块六：家庭协同与亲子沟通训练（家长侧）"),
]

CHAPTER_TITLES = {
    "chapter_1_overview": "整体结果与场景概览",
    "chapter_2_imagery": "沙盘作品意象分析",
    "chapter_3_six_dimensions": "六维方向判定与训练模块指向",
    "chapter_4_academic": "学业成绩与学业评价",
    "chapter_5_risk": "风险研判（九维度分级预警·仅咨询师可见）",
    "chapter_6_interview": "访谈建议",
    "chapter_7_career": "职业发展优势",
    "chapter_8_training_modules": "学习能力训练模块方向建议",
    "chapter_9_general_advice": "总体使用建议",
}

PROTECTIVE_CHAPTER_TITLE = "内在心理资源与保护性因素（发展性视角）"
