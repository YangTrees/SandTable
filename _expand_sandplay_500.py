# -*- coding: utf-8 -*-
"""在 400 件沙具主数据末尾追加 100 件冲突、阴影与中性转化类沙具。"""
from __future__ import annotations

import json
import shutil
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(r"D:\AI\AI_SandBox")
MAIN = ROOT / "assets" / "sandplay_miniatures_500.json"
BACKUP = MAIN.with_name("sandplay_miniatures_500.json.bak_before_expansion_20261120")

SHADOW_PREFIX = (
    "2.5D game asset icon, isometric 45-degree top-down perspective, matte resin and weathered "
    "miniature figurine texture, cool neutral studio lighting with subtle dramatic contrast, "
    "muted dark and desaturated color palette, soft ambient occlusion shadow directly underneath, "
    "isolated on a pure solid white background (#FFFFFF) for easy alpha matting, clean edges, "
    "symbolic psychological sandplay miniature aesthetic, non-gory, high detail, single centered "
    "object, no text, no watermark."
)
NEUTRAL_PREFIX = (
    "2.5D game asset icon, isometric 45-degree top-down perspective, matte resin and fine ceramic "
    "miniature figurine texture, balanced neutral studio lighting, restrained earthy and muted tones "
    "with subtle highlights, soft ambient occlusion shadow directly underneath, isolated on a pure "
    "solid white background (#FFFFFF) for easy alpha matting, clean edges, contemplative sandplay "
    "therapy miniature aesthetic, high detail, single centered object, no text, no watermark."
)

CATEGORIES = [
    ("conflict_combat", "攻击与对抗"),
    ("confinement_pressure", "禁闭与学业重压"),
    ("crisis_decay", "灾害与破损枯竭"),
    ("shadow_figures", "情绪姿态与阴影人物"),
    ("neutral_transformation", "中性张力与转化"),
]

# (id_suffix, name, english_subject, risk_tier, spatial_role, psychology_meaning)
CONFLICT = [
    ("001", "长剑", "long sword", "watch", "threat", "可能象征攻击性、决断与边界维护，也可能反映对力量、惩罚或冲突的恐惧。"),
    ("002", "盾牌", "round shield", "none", "barrier", "可能象征防御、保护与心理边界，也可能提示过度戒备或对外界伤害的高度敏感。"),
    ("003", "弓箭", "bow and arrow", "watch", "threat", "可能象征远距离攻击、目标感与投射，也可能反映回避正面冲突的倾向。"),
    ("004", "匕首", "dagger", "watch", "threat", "可能象征隐秘攻击、切割与关系分离，也可能代表自我保护或难以表达的愤怒。"),
    ("005", "战斧", "battle axe", "high_risk", "threat", "可能象征强烈的攻击性、破坏与权力，也可能反映冲动控制或愤怒释放的需要。"),
    ("006", "长矛", "spear", "watch", "threat", "可能象征直进的目标、攻击与穿刺，也可能提示对方向感和竞争压力的关注。"),
    ("007", "怪兽", "horned monster", "watch", "threat", "可能象征被压抑的原始冲动、恐惧与异己感，也可能代表尚未命名的内在冲突。"),
    ("008", "恶魔", "demon figure", "high_risk", "threat", "可能象征阴影原型、诱惑与禁忌，也可能投射对自身攻击性或失控的恐惧。"),
    ("009", "炸弹", "bomb", "high_risk", "threat", "可能象征积压的愤怒、即将爆发的危机与破坏冲动，也可能提示对失控的担忧。"),
    ("010", "炮台", "artillery cannon", "high_risk", "threat", "可能象征坚固防御、远程威慑与权力，也可能反映对威胁的持续警觉。"),
    ("011", "铁丝网", "barbed wire fence", "watch", "barrier", "可能象征隔离、限制与创伤边界，也可能提示对侵入、伤害或失控的防备。"),
    ("012", "荆棘墙", "thorn wall", "watch", "barrier", "可能象征带刺的边界、保护与惩罚，也可能反映亲近时伴随的疼痛与迟疑。"),
    ("013", "狼牙棒", "spiked club", "high_risk", "threat", "可能象征粗暴力量、惩罚与压迫，也可能投射对权威或身体伤害的恐惧。"),
    ("014", "捕兽夹", "animal trap", "high_risk", "threat", "可能象征埋伏、控制与被困风险，也可能反映对信任或亲密关系中的伤害警觉。"),
    ("015", "燃烧瓶", "molotov cocktail", "high_risk", "threat", "可能象征愤怒的投射、破坏与冲突升级，也可能提示冲动性或报复幻想的张力。"),
    ("016", "手雷", "hand grenade", "high_risk", "threat", "可能象征一触即发的愤怒、危险与失控，也可能反映对冲突后果的强烈担忧。"),
    ("017", "弩箭", "crossbow", "watch", "threat", "可能象征冷静的远射、精确攻击与克制，也可能代表不直接表达的攻击性。"),
    ("018", "盔甲", "suit of armor", "none", "barrier", "可能象征防护、坚硬外壳与角色防御，也可能提示难以卸下的戒备或情感隔离。"),
    ("019", "战旗", "battle flag", "watch", "symbol", "可能象征集体动员、荣誉与对抗立场，也可能反映归属压力或必须选边的焦虑。"),
    ("020", "拳击手套", "boxing gloves", "none", "resource", "可能象征受控的对抗、竞技与力量表达，也可能提示将冲突限制在规则内的需要。"),
]

CONFINEMENT = [
    ("001", "铁牢笼", "iron cage", "watch", "container", "可能象征禁闭、限制与无力感，也可能反映被规则、关系或自我要求困住。"),
    ("002", "锁链", "heavy chain", "watch", "barrier", "可能象征束缚、依附与无法挣脱的责任，也可能提示对自由或分离的渴望。"),
    ("003", "蜘蛛网", "spider web", "watch", "barrier", "可能象征等待、控制与纠缠，也可能反映被关系之网困住或害怕被吞噬。"),
    ("004", "深坑", "deep pit", "high_risk", "threat", "可能象征坠落、空虚与未知恐惧，也可能代表被压抑材料或危机深处的入口。"),
    ("005", "落石陷阱", "falling-rock trap", "high_risk", "threat", "可能象征随时降临的惩罚、埋伏与不安全感，也可能反映对环境威胁的持续警觉。"),
    ("006", "倾斜书山", "tilted mountain of books", "watch", "barrier", "可能象征学业压力、责任堆积与失衡，也可能提示对失败或评价的沉重担忧。"),
    ("007", "考卷堆", "stack of exam papers", "watch", "barrier", "可能象征评价、竞争与未完成的任务，也可能反映对成绩、期待或否定的焦虑。"),
    ("008", "悬崖", "cliff edge", "high_risk", "barrier", "可能象征危险边界、抉择与坠落恐惧，也可能代表站在人生阶段的临界点。"),
    ("009", "死胡同", "dead-end alley", "watch", "barrier", "可能象征无路可走、受限与绝望，也可能反映暂时看不到替代方案的困局。"),
    ("010", "玻璃罩", "glass dome", "watch", "container", "可能象征隔离、保护与窒息，也可能反映被观看却无法呼吸或接触的体验。"),
    ("011", "铁栅栏", "iron fence", "none", "barrier", "可能象征规则、隔离与防御，也可能提示对自由、隐私或身体边界的关注。"),
    ("012", "禁闭室", "locked confinement room", "watch", "container", "可能象征惩罚、孤立与情绪封闭，也可能代表需要独处却害怕被遗忘的矛盾。"),
    ("013", "单向玻璃", "one-way mirror", "watch", "barrier", "可能象征被监视、暴露与不安，也可能反映只能看见外界却无法被看见的孤独。"),
    ("014", "捆绑绳索", "binding ropes", "watch", "barrier", "可能象征束缚、依赖与失去自主，也可能提示关系控制或自我限制的紧张。"),
    ("015", "锁住的日记本", "locked diary", "watch", "symbol", "可能象征被封锁的秘密、羞耻与自我保护，也可能反映渴望被理解却不敢开口。"),
    ("016", "折断的钥匙", "broken key", "none", "symbol", "可能象征失效的解决方式、受阻的准入与挫败，也可能提示求助渠道暂时关闭。"),
    ("017", "沉重镣铐", "heavy shackles", "watch", "barrier", "可能象征长期负担、罪疚与行动受限，也可能反映难以摆脱的责任或旧有角色。"),
    ("018", "狭小暗室", "narrow dark room", "watch", "container", "可能象征退缩、压抑与空间窒息，也可能代表尚未被照亮、需要被看见的内在经验。"),
    ("019", "倒塌书架", "collapsed bookshelf", "watch", "barrier", "可能象征知识秩序崩塌、学业挫败与混乱，也可能反映支撑自我评价的结构松动。"),
    ("020", "高墙围栏", "high enclosing wall", "none", "barrier", "可能象征防御、隔离与领地边界，也可能提示对外界侵入或关系靠近的警惕。"),
]

CRISIS = [
    ("001", "熊熊火焰", "blazing fire", "high_risk", "threat", "可能象征强烈情绪、净化与毁灭性冲动，也可能反映危机中的能量爆发或重生渴望。"),
    ("002", "着火的房子", "burning house", "high_risk", "threat", "可能象征家庭危机、安全感崩塌与内在灼烧，也可能提示愤怒正在侵蚀亲密关系。"),
    ("003", "废墟", "ruins", "watch", "barrier", "可能象征丧失、破坏后的余烬与重建前夜，也可能反映旧身份或旧关系已经瓦解。"),
    ("004", "断桥", "broken bridge", "watch", "barrier", "可能象征连接中断、过渡失败与关系断裂，也可能反映对靠近或离开的双重恐惧。"),
    ("005", "倾覆的小船", "capsized small boat", "watch", "threat", "可能象征失控、漂流与安全感翻覆，也可能提示在情绪风浪中失去方向。"),
    ("006", "枯井", "dry well", "watch", "container", "可能象征资源耗尽、希望落空与深层匮乏，也可能反映内在滋养暂时无法取用。"),
    ("007", "骷髅", "human skull", "watch", "symbol", "可能象征死亡、终结与阴影原型，也可能代表被压抑的记忆或对消亡的恐惧。"),
    ("008", "碎裂的镜子", "shattered mirror", "watch", "symbol", "可能象征自我形象破裂、羞耻与认同危机，也可能反映无法整合的自我片段。"),
    ("009", "暴风雨乌云", "storm cloud", "high_risk", "threat", "可能象征压顶的情绪、威胁与即将到来的冲突，也可能反映长期处于警戒状态。"),
    ("010", "倒塌的树", "fallen tree", "watch", "barrier", "可能象征支撑系统倾倒、生命力受挫与失去庇护，也可能提示旧有依靠不再稳固。"),
    ("011", "干裂的土地", "cracked dry land", "watch", "barrier", "可能象征情感匮乏、滋养中断与长期耗竭，也可能反映对资源与照顾的迫切需求。"),
    ("012", "破旧房屋", "dilapidated house", "watch", "container", "可能象征家庭结构老化、归属感破损与遗忘，也可能代表需要修补的内在居所。"),
    ("013", "烧焦的森林", "charred forest", "high_risk", "barrier", "可能象征大面积创伤、生命力灼伤与集体阴影，也可能提示恢复需要更长时间。"),
    ("014", "折断的箭", "broken arrow", "watch", "symbol", "可能象征目标受挫、攻击失效与方向中断，也可能反映行动力被削弱后的无力感。"),
    ("015", "破碎的陶罐", "shattered clay pot", "none", "symbol", "可能象征容器破裂、情感泄漏与养育受损，也可能代表脆弱自我仍可被修复。"),
    ("016", "漏水的屋顶", "leaking roof", "watch", "container", "可能象征保护失效、边界渗漏与持续消耗，也可能提示家庭或内在空间缺乏遮蔽。"),
    ("017", "沉船", "sunken ship", "watch", "container", "可能象征希望沉没、旅程失败与深层失落，也可能代表被淹没的记忆或未完成的哀悼。"),
    ("018", "熄灭的篝火", "extinguished campfire", "none", "symbol", "可能象征热情消退、群体散场与孤独降临，也可能反映生命力暂时进入低潮。"),
    ("019", "荒芜的田地", "barren field", "watch", "barrier", "可能象征耕耘无果、资源枯竭与等待落空，也可能反映对未来的信心不足。"),
    ("020", "枯萎的花", "withered flower", "watch", "symbol", "可能象征美好凋谢、关系枯萎与生命力下降，也可能提示哀悼与重新滋养的需要。"),
]

SHADOW_FIGURES = [
    ("001", "蹲坐抱膝的少年", "teenager sitting with knees hugged", "watch", "self_proxy", "可能象征退缩、无助与自我安抚，也可能反映在压力下收紧身体、减少外界接触。"),
    ("002", "背对人群的少女", "girl with her back to the crowd", "none", "self_proxy", "可能象征拒绝、疏离与被排斥感，也可能反映需要保留隐私或害怕被评价。"),
    ("003", "捂耳低头的学生", "student covering ears and lowering head", "watch", "self_proxy", "可能象征信息过载、羞耻与逃避评价，也可能提示对批评或噪音的极度敏感。"),
    ("004", "黑色影子人", "black shadow figure", "watch", "self_proxy", "可能象征阴影自我、未整合的冲动与匿名恐惧，也可能代表被压抑而不愿承认的部分。"),
    ("005", "站在悬崖边的人", "person standing at cliff edge", "high_risk", "self_proxy", "可能象征临界抉择、坠落风险与存在性焦虑，也可能反映站在改变门槛前的犹豫。"),
    ("006", "推巨石的人", "person pushing a huge boulder", "watch", "self_proxy", "可能象征沉重责任、徒劳坚持与命运对抗，也可能反映长期承受却难以求助。"),
    ("007", "哭泣的孩子", "crying child", "watch", "self_proxy", "可能象征脆弱、失落与未被安慰的童年自我，也可能提示需要被看见和温柔回应。"),
    ("008", "蜷缩在角落的人", "person curled up in a corner", "watch", "self_proxy", "可能象征恐惧、退缩与自我保护，也可能反映在关系中缺乏安全空间。"),
    ("009", "抱头蹲下的成年人", "adult crouching and holding head", "watch", "self_proxy", "可能象征崩溃边缘、羞耻与无法承受的压力，也可能代表退行到需要被保护的状态。"),
    ("010", "背对镜子的女孩", "girl with her back to a mirror", "watch", "self_proxy", "可能象征回避自我审视、羞耻与认同冲突，也可能反映不愿面对身体或内在形象。"),
    ("011", "捂脸站立的人", "person standing with face covered", "watch", "self_proxy", "可能象征羞耻、隐藏与情绪淹没，也可能提示对暴露真实自我的强烈不安。"),
    ("012", "低头独行的少年", "boy walking alone with head down", "watch", "self_proxy", "可能象征孤独、内疚与与群体脱节，也可能反映在压力中独自承担、不愿求助。"),
    ("013", "双臂交叉的少女", "girl with arms crossed", "none", "self_proxy", "可能象征防御、拒绝与边界维护，也可能反映亲密关系中的不信任或自我保护。"),
    ("014", "躲在门后的人", "person hiding behind a door", "watch", "self_proxy", "可能象征观望、迟疑与害怕进入，也可能代表在关系门口既渴望又退缩。"),
    ("015", "抱膝坐地的老人", "elderly person sitting with knees hugged", "watch", "self_proxy", "可能象征孤独、回忆与生命力收缩，也可能反映被遗忘或需要陪伴的深层渴望。"),
    ("016", "背负重物弯腰的人", "person bent under a heavy load", "watch", "self_proxy", "可能象征长期负担、责任压迫与隐忍，也可能提示已经超出承受范围却仍在坚持。"),
    ("017", "伸手求助的人", "person reaching out for help", "none", "self_proxy", "可能象征求助意愿、脆弱暴露与连接需要，也可能反映对回应不确定的试探。"),
    ("018", "背对光站立的人", "person standing with back to the light", "watch", "self_proxy", "可能象征拒绝希望、沉浸在阴影与自我隔绝，也可能代表尚未准备好转向资源。"),
    ("019", "蹲在阴影里的男孩", "boy crouching in shadow", "watch", "self_proxy", "可能象征被忽略、恐惧与低自我价值，也可能反映在家庭或群体中缺少位置。"),
    ("020", "掩面而坐的人", "person sitting silently with face buried in hands", "watch", "self_proxy", "可能象征羞耻、哀伤与不愿被看见，也可能提示情绪过于强烈而需要暂时遮蔽。"),
]

NEUTRAL = [
    ("001", "独立面具", "standalone mask", "none", "symbol", "可能象征角色面具、社会适应与真实自我的距离，也可能代表可被选择而非固定的身份。"),
    ("002", "完整镜子", "intact mirror", "none", "symbol", "可能象征自我映照、整合与如实看见，也可能提示对认同和关系真相的探索。"),
    ("003", "天平", "balance scale", "none", "symbol", "可能象征权衡、公平与责任分配，也可能反映在冲突中寻找中立与可承受的平衡。"),
    ("004", "破茧的蚕茧", "cocoon being broken open", "none", "symbol", "可能象征旧壳破裂、艰难转化与新生，也可能反映改变虽痛苦却已经不可逆地开始。"),
    ("005", "发芽的枯木", "sprouting dead tree", "none", "resource", "可能象征枯竭后的复苏、韧性与希望，也可能提示生命力在看似停滞处重新启动。"),
    ("006", "裂缝中的小花", "small flower growing from a crack", "none", "resource", "可能象征创伤缝隙里的希望、柔韧与新生，也可能反映微小资源正在恢复。"),
    ("007", "灭火器", "fire extinguisher", "none", "resource", "可能象征情绪降温、危机控制与边界设置，也可能提示需要中止冲突、保护现场。"),
    ("008", "救生圈", "lifebuoy", "none", "resource", "可能象征被托住、求助与安全恢复，也可能反映在情绪风浪中寻找可依靠的资源。"),
    ("009", "急救箱", "first-aid kit", "none", "resource", "可能象征修复、照料与应急支持，也可能提示旧伤需要被处理而非继续压抑。"),
    ("010", "空鸟笼", "empty birdcage with open door", "none", "container", "可能象征束缚解除、自由与失去陪伴，也可能反映开放边界后既轻松又空落的感觉。"),
    ("011", "打开的门锁", "open door lock", "none", "connector", "可能象征准入、解禁与新阶段，也可能反映机会出现后仍需要决定是否跨过门槛。"),
    ("012", "连接两岸的石桥", "stone bridge connecting two banks", "none", "connector", "可能象征稳固连接、过渡与关系修复，也可能提示需要耐心搭建可承受的通道。"),
    ("013", "重新点燃的蜡烛", "relit candle", "none", "symbol", "可能象征希望重燃、仪式与微弱但持续的坚持，也可能反映哀悼后重新投入生活。"),
    ("014", "修补过的陶罐", "repaired clay pot", "none", "container", "可能象征破损后的修复、接纳与延续，也可能反映伤痕被整合而非被抹去。"),
    ("015", "新生的嫩芽", "fresh sprout", "none", "resource", "可能象征新开始、潜能与柔软生命力，也可能提示改变需要被保护和耐心照料。"),
    ("016", "展开的双手", "open palms", "none", "symbol", "可能象征开放、接纳与求助，也可能反映愿意放下防御、允许关系靠近。"),
    ("017", "解开的绳结", "untied knot", "none", "symbol", "可能象征束缚松开、冲突缓和与关系解套，也可能提示旧有纠缠正在被理清。"),
    ("018", "透光的窗", "window letting light through", "none", "connector", "可能象征希望、视野与内外交流，也可能反映封闭空间中仍保留的通向外界之处。"),
    ("019", "立在中线的白旗", "white flag at the center line", "none", "symbol", "可能象征停战、界限与暂时休整，也可能反映冲突双方需要重新谈判的愿望。"),
    ("020", "指南针", "compass", "none", "symbol", "可能象征方向、价值参照与内在指引，也可能提示在混乱中寻找可依循的坐标。"),
]

GROUPS = [
    ("CONFLICT", "conflict_combat", "攻击与对抗", SHADOW_PREFIX, CONFLICT),
    ("CONFINEMENT", "confinement_pressure", "禁闭与学业重压", SHADOW_PREFIX, CONFINEMENT),
    ("CRISIS", "crisis_decay", "灾害与破损枯竭", SHADOW_PREFIX, CRISIS),
    ("SHADOW", "shadow_figures", "情绪姿态与阴影人物", SHADOW_PREFIX, SHADOW_FIGURES),
    ("NEUTRAL", "neutral_transformation", "中性张力与转化", NEUTRAL_PREFIX, NEUTRAL),
]


def main() -> None:
    data = json.loads(MAIN.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
    if data.get("total_count") != 400 or len(data["items"]) != 400:
        raise SystemExit(f"当前不是 400 条：total={data.get('total_count')} items={len(data['items'])}")

    existing_names = {item["name"] for item in data["items"]}
    existing_ids = {item["id"] for item in data["items"]}
    new_items: list[OrderedDict] = []
    seen_names: set[str] = set()

    for id_prefix, category_code, category_name, prefix, rows in GROUPS:
        if len(rows) != 20:
            raise SystemExit(f"{category_name} 数量不是 20：{len(rows)}")
        for suffix, name, subject, risk, role, meaning in rows:
            if name in existing_names or name in seen_names:
                raise SystemExit(f"新增沙具重名：{name}")
            if len(meaning) < 35:
                meaning = "在箱庭中，" + meaning
            if not 35 <= len(meaning) <= 60:
                raise SystemExit(f"释义长度不合规({len(meaning)})：{name} {meaning}")
            seen_names.add(name)
            item_id = f"{id_prefix}_{suffix}"
            if item_id in existing_ids:
                raise SystemExit(f"新增 ID 重复：{item_id}")
            existing_ids.add(item_id)
            new_items.append(OrderedDict([
                ("id", item_id),
                ("name", name),
                ("category", category_name),
                ("risk_tier", risk),
                ("spatial_role", role),
                ("psychology_meaning", meaning),
                ("prompt", f"{prefix} Subject: {subject}."),
            ]))

    if len(new_items) != 100:
        raise SystemExit(f"新增数量不是 100：{len(new_items)}")

    # 7 件既有阴影沙具统一改用 shadow 前缀，保留原主语。
    shadow_ids = {
        "VEHICLE_016", "VEHICLE_017", "MYSTIC_012", "NATURE_036",
        "NATURE_009", "ANIMAL_034", "ANIMAL_063",
    }
    touched = 0
    for item in data["items"]:
        if item["id"] in shadow_ids:
            if " Subject: " not in item["prompt"]:
                raise SystemExit(f"无法解析原 prompt 主语：{item['id']}")
            subject = item["prompt"].split(" Subject: ", 1)[1].strip().rstrip(".")
            item["prompt"] = f"{SHADOW_PREFIX} Subject: {subject}."
            touched += 1
    if touched != 7:
        raise SystemExit(f"替换阴影前缀数量异常：{touched}")

    # 在 style_prefix 后插入两套新前缀，其余顶层键顺序保持不变。
    rebuilt = OrderedDict()
    for key, value in data.items():
        rebuilt[key] = value
        if key == "style_prefix":
            rebuilt["style_prefix_shadow"] = SHADOW_PREFIX
            rebuilt["style_prefix_neutral"] = NEUTRAL_PREFIX
    data = rebuilt

    # 追加分类与 100 条新记录。
    new_categories = []
    for id_prefix, category_code, category_name, prefix, rows in GROUPS:
        new_categories.append(OrderedDict([
            ("code", category_code),
            ("name", category_name),
            ("count", len(rows)),
        ]))
    data["categories"].extend(new_categories)
    data["items"].extend(new_items)
    data["total_count"] = len(data["items"])

    if len(data["items"]) != 500:
        raise SystemExit(f"总数不是 500：{len(data['items'])}")
    if sum(c["count"] for c in data["categories"]) != 500:
        raise SystemExit("分类计数合计不是 500")
    if len({item["id"] for item in data["items"]}) != 500:
        raise SystemExit("ID 不唯一")
    if len({item["name"] for item in data["items"]}) != 500:
        raise SystemExit("名称不唯一")

    if not BACKUP.exists():
        shutil.copy2(MAIN, BACKUP)
    MAIN.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("total", data["total_count"])
    print("new_items", len(new_items))
    print("shadow_rewritten", touched)
    print("categories", [(c["code"], c["count"]) for c in data["categories"][-5:]])
    print("risk", dict(Counter(item["risk_tier"] for item in data["items"])))
    print("role", dict(Counter(item["spatial_role"] for item in data["items"])))
    print("backup", BACKUP)


if __name__ == "__main__":
    main()
