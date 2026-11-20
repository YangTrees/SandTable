# -*- coding: utf-8 -*-
"""生成 500 个心理沙盘沙具 JSON 字典。"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "sandplay_miniatures_500.json"

STYLE_PREFIX = (
    "2.5D game asset icon, isometric 45-degree top-down perspective, "
    "soft clay and matte resin miniature figurine texture, warm studio lighting, "
    "soft ambient occlusion shadow directly underneath, isolated on a pure solid white background "
    "(#FFFFFF) for easy alpha matting, clean edges, cohesive healing sandplay therapy aesthetic, "
    "high detail, single centered object, no text, no watermark."
)

CATEGORIES = [
    {
        "code": "person_role",
        "name": "人物与角色原型",
        "prefix": "PERSON",
        "expected": 80,
        "default_aspect": "人际角色、依恋关系、自我认同与社会角色投射",
        "items": [
            ("爷爷", "grandfather"), ("奶奶", "grandmother"), ("外公", "maternal grandfather"), ("外婆", "maternal grandmother"),
            ("父亲", "father"), ("母亲", "mother"), ("婴儿", "baby"), ("小男孩", "young boy"),
            ("小女孩", "young girl"), ("青少年男孩", "teenage boy"), ("青少年女孩", "teenage girl"), ("哥哥", "older brother"),
            ("姐姐", "older sister"), ("弟弟", "younger brother"), ("妹妹", "younger sister"), ("家庭合影人物", "family group figure"),
            ("男老师", "male teacher"), ("女老师", "female teacher"), ("班主任", "homeroom teacher"), ("心理老师", "school counselor"),
            ("图书管理员", "librarian"), ("男学生", "male student"), ("女学生", "female student"), ("看书少年", "reading boy"),
            ("写作业学生", "student doing homework"), ("举手学生", "student raising hand"), ("背书包学生", "student with backpack"), ("小组讨论学生", "students in discussion"),
            ("警察", "police officer"), ("军人", "soldier"), ("士兵", "guard soldier"), ("卫兵", "sentry"),
            ("消防员", "firefighter"), ("医生", "doctor"), ("护士", "nurse"), ("心理咨询师", "therapist"),
            ("宇航员", "astronaut"), ("飞行员", "pilot"), ("司机", "driver"), ("工人", "worker"),
            ("农民", "farmer"), ("厨师", "chef"), ("科学家", "scientist"), ("运动员", "athlete"),
            ("舞者", "dancer"), ("音乐家", "musician"), ("画家", "artist"), ("园丁", "gardener"),
            ("国王", "king"), ("王后", "queen"), ("王子", "prince"), ("公主", "princess"),
            ("巫师", "wizard"), ("魔法师", "mage"), ("骑士", "knight"), ("天使", "angel"),
            ("小精灵", "fairy"), ("智者老人", "wise elder"), ("英雄少年", "young hero"), ("旅人", "traveler"),
            ("隐士", "hermit"), ("先知", "prophet"), ("守门人", "gatekeeper"), ("蒙面人", "masked figure"),
            ("小丑", "clown"), ("木偶人", "puppet"), ("机器人", "robot"), ("外星人", "alien"),
            ("超人", "superhero"), ("守护者", "guardian figure"), ("探索者", "explorer"), ("迷路者", "lost child"),
            ("疗愈者", "healer"), ("观察者", "observer"), ("领导者", "leader"), ("跟随者", "follower"),
            ("朋友", "friend"), ("同伴", "companion"), ("对手", "opponent"), ("倾听者", "listener"),
        ],
    },
    {
        "code": "building_home",
        "name": "建筑与居所",
        "prefix": "BUILDING",
        "expected": 70,
        "default_aspect": "安全容器、空间边界、归属感和外部支持结构",
        "items": [
            ("温馨小屋", "cozy cottage"), ("现代学校", "modern school"), ("教学楼", "classroom building"), ("图书馆", "library"),
            ("教室", "classroom"), ("学生宿舍", "dormitory"), ("家庭住宅", "family house"), ("庭院", "courtyard"),
            ("城堡", "castle"), ("高塔", "tower"), ("灯塔", "lighthouse"), ("桥梁", "bridge"),
            ("木桥", "wooden bridge"), ("石桥", "stone bridge"), ("栅栏", "fence"), ("围墙", "wall"),
            ("篱笆", "hedge fence"), ("岗哨", "guard post"), ("瞭望塔", "watchtower"), ("医院", "hospital"),
            ("诊所", "clinic"), ("车站", "train station"), ("机场", "airport"), ("码头", "harbor"),
            ("商店", "shop"), ("市场", "market hall"), ("博物馆", "museum"), ("体育馆", "gymnasium"),
            ("游乐场", "playground"), ("公园大门", "park gate"), ("寺庙", "temple"), ("道观", "taoist temple"),
            ("教堂", "church"), ("塔楼", "pagoda tower"), ("钟楼", "bell tower"), ("风车房", "windmill house"),
            ("农舍", "farmhouse"), ("谷仓", "barn"), ("水井房", "well house"), ("山洞入口", "cave entrance"),
            ("隧道", "tunnel"), ("城门", "city gate"), ("城墙", "city wall"), ("拱门", "archway"),
            ("亭子", "pavilion"), ("长廊", "covered corridor"), ("台阶", "stone steps"), ("大门", "doorway"),
            ("木窗", "wooden window"), ("屋顶", "rooftop"), ("烟囱", "chimney"), ("帐篷", "tent"),
            ("树屋", "tree house"), ("冰屋", "igloo"), ("天文台", "observatory"), ("科学实验室", "science laboratory"),
            ("车站站台", "station platform"), ("电话亭", "telephone booth"), ("公交站", "bus stop"), ("地下车库入口", "underground garage entrance"),
            ("安全岛", "safety island"), ("圆形广场", "circular plaza"), ("喷泉广场", "fountain plaza"), ("纪念碑", "monument"),
            ("雕像基座", "statue pedestal"), ("花园凉亭", "garden gazebo"), ("阳台", "balcony"), ("楼梯间", "stairwell"),
            ("天台", "rooftop terrace"), ("小型灯塔小屋", "beacon cottage"),
        ],
    },
    {
        "code": "nature_plant",
        "name": "自然山水与植物",
        "prefix": "NATURE",
        "expected": 80,
        "default_aspect": "生命力、情绪流动、成长节律、自然滋养与转化",
        "items": [
            ("常绿大树", "evergreen tree"), ("松树", "pine tree"), ("柏树", "cypress tree"), ("柳树", "willow tree"),
            ("梧桐树", "plane tree"), ("白杨树", "poplar tree"), ("秋日红枫", "red maple tree"), ("银杏树", "ginkgo tree"),
            ("枯树", "withered tree"), ("开花树", "flowering tree"), ("樱花树", "cherry blossom tree"), ("桃树", "peach tree"),
            ("梨树", "pear tree"), ("苹果树", "apple tree"), ("椰子树", "coconut palm"), ("棕榈树", "palm tree"),
            ("仙人掌", "cactus"), ("多肉植物", "succulent plant"), ("向日葵", "sunflower"), ("玫瑰花丛", "rose bush"),
            ("郁金香", "tulip"), ("百合花", "lily"), ("菊花", "chrysanthemum"), ("梅花", "plum blossom"),
            ("兰花", "orchid"), ("竹子", "bamboo"), ("草丛", "grass clump"), ("灌木", "shrub"),
            ("藤蔓", "vine"), ("苔藓", "moss patch"), ("蘑菇", "mushroom"), ("大树桩", "tree stump"),
            ("落叶堆", "fallen leaves"), ("高山", "mountain"), ("雪山", "snowy mountain"), ("火山", "volcano"),
            ("丘陵", "hill"), ("假山", "rockery"), ("岩石", "rock"), ("巨石", "boulder"),
            ("卵石", "pebbles"), ("沙滩", "sandy beach"), ("沙漠", "desert"), ("绿洲", "oasis"),
            ("岛屿", "island"), ("半岛", "peninsula"), ("湖泊", "lake"), ("河流", "river"),
            ("溪流", "stream"), ("瀑布", "waterfall"), ("池塘", "pond"), ("水井", "water well"),
            ("海洋", "ocean"), ("海浪", "ocean wave"), ("珊瑚", "coral"), ("贝壳", "seashell"),
            ("海螺", "conch shell"), ("海星", "starfish"), ("云朵", "cloud"), ("太阳", "sun"),
            ("月亮", "moon"), ("星星", "star"), ("彩虹", "rainbow"), ("雨滴", "raindrop"),
            ("雪花", "snowflake"), ("雷电", "lightning bolt"), ("风", "swirl of wind"), ("雾", "mist"),
            ("山径", "mountain path"), ("田间小路", "country path"), ("森林", "forest"), ("草原", "grassland"),
            ("花田", "flower field"), ("稻田", "rice field"), ("麦田", "wheat field"), ("荷塘", "lotus pond"),
            ("泉水", "spring water"), ("小水洼", "puddle"), ("冰面", "frozen surface"), ("彩虹桥", "rainbow arch"),
        ],
    },
    {
        "code": "animal_myth",
        "name": "动物与神兽",
        "prefix": "ANIMAL",
        "expected": 80,
        "default_aspect": "本能能量、情绪力量、关系模式、文化原型与潜在资源",
        "items": [
            ("猫", "cat"), ("狗", "dog"), ("兔子", "rabbit"), ("仓鼠", "hamster"),
            ("豚鼠", "guinea pig"), ("鹦鹉", "parrot"), ("金鱼", "goldfish"), ("乌龟", "tortoise"),
            ("鹿", "deer"), ("狐狸", "fox"), ("熊", "bear"), ("松鼠", "squirrel"),
            ("刺猬", "hedgehog"), ("熊猫", "panda"), ("猴子", "monkey"), ("马", "horse"),
            ("牛", "cow"), ("羊", "goat"), ("猪", "pig"), ("鸡", "chicken"),
            ("鸭", "duck"), ("鹅", "goose"), ("狮子", "lion"), ("老虎", "tiger"),
            ("狼", "wolf"), ("豹", "leopard"), ("大象", "elephant"), ("长颈鹿", "giraffe"),
            ("斑马", "zebra"), ("犀牛", "rhinoceros"), ("河马", "hippopotamus"), ("骆驼", "camel"),
            ("袋鼠", "kangaroo"), ("蛇", "snake"), ("蜥蜴", "lizard"), ("青蛙", "frog"),
            ("鳄鱼", "crocodile"), ("白鸽", "white dove"), ("猫头鹰", "owl"), ("老鹰", "eagle"),
            ("燕子", "swallow"), ("麻雀", "sparrow"), ("孔雀", "peacock"), ("天鹅", "swan"),
            ("鹤", "crane"), ("企鹅", "penguin"), ("海鸥", "seagull"), ("鲸鱼", "whale"),
            ("海豚", "dolphin"), ("海龟", "sea turtle"), ("鲨鱼", "shark"), ("章鱼", "octopus"),
            ("水母", "jellyfish"), ("螃蟹", "crab"), ("虾", "shrimp"), ("海马", "seahorse"),
            ("蝴蝶", "butterfly"), ("蜜蜂", "bee"), ("蜻蜓", "dragonfly"), ("瓢虫", "ladybug"),
            ("蚂蚁", "ant"), ("蜗牛", "snail"), ("蜘蛛", "spider"), ("蝉", "cicada"),
            ("青龙", "azure dragon"), ("白虎", "white tiger"), ("朱雀", "vermilion bird"), ("玄武", "black tortoise"),
            ("麒麟", "qilin"), ("凤凰", "phoenix"), ("中国龙", "chinese dragon"), ("貔貅", "pixiu"),
            ("白泽", "baize"), ("九尾狐", "nine-tailed fox"), ("天马", "winged horse"), ("独角兽", "unicorn"),
            ("狮鹫", "griffin"), ("小神龙", "little guardian dragon"), ("守护神兽", "guardian beast"), ("仙鹤", "immortal crane"),
        ],
    },
    {
        "code": "vehicle_tool",
        "name": "交通工具与现代器物",
        "prefix": "VEHICLE",
        "expected": 60,
        "default_aspect": "行动方向、目标推进、控制感、速度感与阶段转换",
        "items": [
            ("家用轿车", "family car"), ("校车", "school bus"), ("公交车", "city bus"), ("警车", "police car"),
            ("救护车", "ambulance"), ("消防车", "fire truck"), ("出租车", "taxi"), ("自行车", "bicycle"),
            ("电动车", "electric scooter"), ("摩托车", "motorcycle"), ("三轮车", "tricycle"), ("卡车", "truck"),
            ("货车", "cargo van"), ("工程车", "construction vehicle"), ("挖掘机", "excavator"), ("坦克", "tank"),
            ("战车", "armored vehicle"), ("帆船", "sailboat"), ("轮船", "ship"), ("游艇", "yacht"),
            ("渔船", "fishing boat"), ("皮划艇", "kayak"), ("潜艇", "submarine"), ("飞机", "airplane"),
            ("直升机", "helicopter"), ("火箭", "rocket"), ("热气球", "hot air balloon"), ("飞艇", "airship"),
            ("高铁", "high-speed train"), ("火车", "train"), ("地铁", "subway train"), ("缆车", "cable car"),
            ("红绿灯", "traffic light"), ("路标", "road sign"), ("路灯", "street lamp"), ("斑马线", "crosswalk"),
            ("加油站", "gas station"), ("充电桩", "charging station"), ("电话", "telephone"), ("手机", "smartphone"),
            ("电脑", "computer"), ("平板电脑", "tablet"), ("电视", "television"), ("收音机", "radio"),
            ("相机", "camera"), ("摄像机", "video camera"), ("机器人玩具", "toy robot"), ("无人机", "drone"),
            ("卫星", "satellite"), ("望远镜", "binoculars"), ("微波炉", "microwave oven"), ("冰箱", "refrigerator"),
            ("洗衣机", "washing machine"), ("电风扇", "electric fan"), ("台灯", "desk lamp"), ("闹钟", "alarm clock"),
            ("电梯", "elevator"), ("自动扶梯", "escalator"), ("自动售货机", "vending machine"), ("音响", "speaker"),
        ],
    },
    {
        "code": "study_life",
        "name": "学习与生活道具",
        "prefix": "STUDY",
        "expected": 50,
        "default_aspect": "学习动力、成就体验、时间管理、生活秩序与自我效能",
        "items": [
            ("书桌", "desk"), ("课桌", "school desk"), ("椅子", "chair"), ("黑板", "blackboard"),
            ("白板", "whiteboard"), ("讲台", "lectern"), ("书本", "book"), ("书本堆", "stack of books"),
            ("打开的书", "open book"), ("笔记本", "notebook"), ("铅笔", "pencil"), ("钢笔", "fountain pen"),
            ("尺子", "ruler"), ("橡皮", "eraser"), ("文具盒", "pencil case"), ("书包", "schoolbag"),
            ("奖杯", "trophy"), ("奖状", "certificate"), ("奖牌", "medal"), ("时钟", "clock"),
            ("沙漏", "hourglass"), ("日历", "calendar"), ("地球仪", "globe"), ("地图", "map"),
            ("显微镜", "microscope"), ("望远镜", "telescope"), ("放大镜", "magnifying glass"), ("计算器", "calculator"),
            ("实验烧杯", "beaker"), ("试管架", "test tube rack"), ("拼图", "jigsaw puzzle"), ("积木", "building blocks"),
            ("棋盘", "board game"), ("围棋盘", "go board"), ("象棋盘", "chinese chess board"), ("魔方", "rubik's cube"),
            ("画笔", "paintbrush"), ("调色盘", "paint palette"), ("画板", "drawing board"), ("音乐盒", "music box"),
            ("钢琴", "piano"), ("小提琴", "violin"), ("吉他", "guitar"), ("秋千", "swing"),
            ("滑梯", "slide"), ("跷跷板", "seesaw"), ("木马", "rocking horse"), ("皮球", "ball"),
            ("跳绳", "jump rope"), ("钥匙", "key"),
        ],
    },
    {
        "code": "mystic_symbol",
        "name": "神秘与象征符号",
        "prefix": "MYSTIC",
        "expected": 40,
        "default_aspect": "无意识象征、文化意义、未知探索、希望、转化与整合",
        "items": [
            ("太极图", "taiji symbol"), ("八卦镜", "bagua mirror"), ("水晶球", "crystal ball"), ("许愿池", "wishing well"),
            ("篝火", "campfire"), ("蜡烛", "candle"), ("灯笼", "lantern"), ("红旗", "red flag"),
            ("蓝旗", "blue flag"), ("白旗", "white flag"), ("彩旗", "colorful flag"), ("墓碑", "tombstone"),
            ("十字架", "cross"), ("佛像", "buddha statue"), ("莲花座", "lotus pedestal"), ("香炉", "incense burner"),
            ("符咒卷轴", "talisman scroll"), ("迷宫入口", "maze entrance"), ("迷宫中心", "maze center"), ("魔法阵", "magic circle"),
            ("星盘", "astrolabe"), ("月亮图腾", "moon totem"), ("太阳图腾", "sun totem"), ("神秘门扉", "mysterious door"),
            ("古老钥匙孔", "ancient keyhole"), ("宝箱", "treasure chest"), ("藏宝图", "treasure map"), ("魔法书", "spell book"),
            ("魔杖", "magic wand"), ("圣杯", "holy grail"), ("祭坛", "altar"), ("神像", "deity statue"),
            ("守护符文石", "guardian rune stone"), ("图腾柱", "totem pole"), ("捕梦网", "dreamcatcher"), ("风铃", "wind chime"),
            ("水晶石", "crystal stone"), ("龙珠", "dragon pearl"), ("能量石", "energy stone"), ("心灵之树", "tree of soul"),
        ],
    },
    {
        "code": "food_abundance",
        "name": "饮食与丰饶意象",
        "prefix": "FOOD",
        "expected": 40,
        "default_aspect": "滋养、照料、家庭支持、资源感、丰饶与基本安全感",
        "items": [
            ("餐桌", "dining table"), ("圆桌宴席", "round banquet table"), ("蛋糕", "cake"), ("生日蛋糕", "birthday cake"),
            ("面包", "bread"), ("水果篮", "fruit basket"), ("苹果", "apple"), ("香蕉", "banana"),
            ("橙子", "orange"), ("葡萄", "grapes"), ("西瓜", "watermelon"), ("草莓", "strawberry"),
            ("桃子", "peach"), ("梨", "pear"), ("石榴", "pomegranate"), ("稻田", "rice paddy"),
            ("麦田", "wheat field"), ("粮仓", "granary"), ("米袋", "rice sack"), ("面袋", "flour sack"),
            ("玉米", "corn"), ("南瓜", "pumpkin"), ("胡萝卜", "carrot"), ("白菜", "cabbage"),
            ("蔬菜篮", "vegetable basket"), ("鸡蛋", "egg"), ("牛奶", "milk bottle"), ("茶壶", "teapot"),
            ("茶杯", "tea cup"), ("水杯", "water cup"), ("水壶", "kettle"), ("水井", "water well"),
            ("水桶", "water bucket"), ("蜂蜜罐", "honey jar"), ("糖果罐", "candy jar"), ("巧克力盒", "chocolate box"),
            ("饼干盘", "cookie plate"), ("火锅", "hot pot"), ("碗筷套装", "bowl and chopsticks"), ("汤碗", "soup bowl"),
        ],
    },
]

MEANING_RULES = [
    (("父", "母", "爷爷", "奶奶", "外公", "外婆", "家庭", "哥哥", "姐姐", "弟弟", "妹妹"), "家庭支持、依恋关系、照顾者形象与安全感来源"),
    (("老师", "班主任", "学生", "学校", "教室", "课桌", "黑板", "书本", "书包", "图书"), "学习动力、学校适应、师生关系、规则感与知识获得"),
    (("警察", "军人", "士兵", "卫兵", "岗哨", "瞭望塔", "栅栏", "围墙", "篱笆", "城墙", "城门"), "边界防御、规则意识、安全警戒与自我保护"),
    (("医生", "护士", "心理咨询", "疗愈", "医院", "诊所", "救护车"), "被照顾、修复资源、求助意愿与支持系统"),
    (("国王", "王后", "领导", "权威"), "权威形象、掌控感、理想化角色与自我力量"),
    (("巫师", "魔法", "圣杯", "祭坛", "符文", "水晶", "能量"), "潜能、转化、意义建构与内在资源激活"),
    (("骑士", "英雄", "守护", "超人"), "勇气、保护欲、行动力和应对困难的英雄原型"),
    (("天使", "精灵", "佛", "莲花", "仙鹤"), "希望、慈悲、精神支持、纯净与超越性资源"),
    (("智者", "老人", "先知", "灯塔", "望远镜"), "智慧老人原型、引导、远见、目标与内在指引"),
    (("蒙面", "小丑", "木偶", "阴影"), "人格面具、阴影材料、情绪防御与未被表达的自我"),
    (("桥", "彩虹桥"), "连接、过渡、沟通、阶段转换与整合可能"),
    (("小屋", "住宅", "庭院", "家", "帐篷", "树屋", "冰屋"), "安全容器、归属感、私人空间与内在居所"),
    (("车站", "机场", "码头", "隧道", "门", "台阶"), "过渡阶段、出发与抵达、选择节点和未来方向"),
    (("树", "竹", "花", "草", "苗", "稻", "麦"), "成长、生命力、韧性、滋养与个体发展"),
    (("枯树", "落叶", "荒漠", "沙漠"), "能量耗竭、停滞感、资源不足或等待恢复的状态"),
    (("山", "岩石", "巨石", "丘陵", "假山"), "稳定性、压力承载、挑战、屏障与坚持"),
    (("水", "湖", "河", "溪", "海", "瀑布", "泉", "池塘", "井"), "情绪流动、无意识内容、滋养与生命之源"),
    (("岛", "半岛"), "自我空间、独立性、孤立感或与外界连接的程度"),
    (("太阳", "月亮", "星", "彩虹", "云朵", "雨", "雪", "雷", "风", "雾"), "情绪基调、能量状态、希望、变化与氛围"),
    (("猫", "狐狸", "刺猬"), "独立性、警觉、边界感与细腻的自我保护"),
    (("狗", "马", "牛", "羊"), "忠诚、支持、行动力、耐力与关系中的稳定感"),
    (("兔", "仓鼠", "豚鼠", "鹿"), "敏感、温和、脆弱感与需要被保护的部分"),
    (("熊", "狮", "虎", "狼", "豹", "象", "犀牛"), "力量、攻击性、勇气、控制感与本能能量"),
    (("蛇", "蜥蜴", "鳄鱼", "蜘蛛"), "转化、警觉、阴影材料、潜在威胁感或本能反应"),
    (("鸟", "鸽", "鹰", "燕", "雀", "天鹅", "鹤", "鸥"), "自由、视野、目标、和平与超越性愿望"),
    (("鲸", "海豚", "海龟", "鲨鱼", "水母", "章鱼"), "深层情绪、沟通、适应能力、潜在压力或无意识能量"),
    (("蝴蝶", "蜜蜂", "蜻蜓", "瓢虫", "蚂蚁", "蜗牛", "蝉"), "微小但持续的变化、合作、节奏、耐心与转化"),
    (("青龙", "白虎", "朱雀", "玄武", "麒麟", "凤凰", "龙", "貔貅", "白泽", "九尾狐", "天马", "独角兽", "狮鹫", "神兽"), "中国文化原型、守护力量、祥瑞、转化与集体无意识象征"),
    (("警车", "红绿灯", "路标", "斑马线"), "规则、秩序、边界、外部约束与安全通行"),
    (("救护", "消防"), "紧急支持、修复资源、危机应对与保护"),
    (("坦克", "战车"), "强防御、攻击性、警戒感与高压应对方式"),
    (("车", "船", "飞机", "火箭", "列车", "地铁", "高铁", "自行车", "摩托车", "热气球", "飞艇"), "行动方向、目标推进、自主性、速度与阶段转换"),
    (("时钟", "沙漏", "日历", "闹钟"), "时间感、紧迫感、计划性与自我管理"),
    (("奖杯", "奖状", "奖牌"), "成就体验、外部评价、胜任感与目标认可"),
    (("钥匙", "锁", "门扉"), "开启资源、解决路径、潜能释放与新的可能性"),
    (("秋千", "滑梯", "跷跷板", "木马", "皮球", "跳绳"), "游戏性、童真、情绪释放、身体能量与快乐体验"),
    (("太极", "八卦"), "阴阳平衡、对立整合、中国文化象征与内在调和"),
    (("许愿", "篝火", "蜡烛", "灯笼", "彩旗"), "愿望、希望、仪式感和情绪点亮"),
    (("墓碑", "十字", "神像", "图腾"), "终结、纪念、信仰、意义与转化主题"),
    (("迷宫", "藏宝图", "宝箱"), "探索、困惑、寻找资源、目标发现与自我整合"),
    (("餐桌", "宴席", "蛋糕", "面包", "水果", "蔬菜", "鸡蛋", "牛奶", "茶", "水杯", "蜂蜜", "糖果", "巧克力", "饼干", "火锅", "碗筷"), "滋养、照料、家庭氛围、奖赏体验与基本安全感"),
    (("粮仓", "米袋", "面袋", "玉米", "南瓜", "石榴"), "资源储备、丰饶感、成长基础与持续支持"),
]


def build_meaning(name: str, default_aspect: str) -> str:
    aspect = default_aspect
    for keywords, text in MEANING_RULES:
        if any(keyword in name for keyword in keywords):
            aspect = text
            break
    return f"在发展性心理沙盘中，可作为{aspect}的探索性观察线索；具体含义需结合空间位置、组合关系和访谈确认。"


def main() -> None:
    items = []
    categories_meta = []

    for category in CATEGORIES:
        expected = category["expected"]
        actual = len(category["items"])
        if actual != expected:
            raise ValueError(f"{category['name']} 数量错误：期望 {expected}，实际 {actual}")

        categories_meta.append({
            "code": category["code"],
            "name": category["name"],
            "count": actual,
        })

        for index, (name, english_name) in enumerate(category["items"], start=1):
            item_id = f"{category['prefix']}_{index:03d}"
            prompt = f"{STYLE_PREFIX} Subject: {english_name}."
            items.append({
                "id": item_id,
                "name": name,
                "category": category["name"],
                "psychology_meaning": build_meaning(name, category["default_aspect"]),
                "prompt": prompt,
            })

    if len(items) != 500:
        raise ValueError(f"总数量错误：期望 500，实际 {len(items)}")

    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "total_count": len(items),
        "style_prefix": STYLE_PREFIX,
        "categories": categories_meta,
        "items": items,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {OUTPUT}")
    print(f"total: {len(items)}")
    for meta in categories_meta:
        print(f"{meta['code']}: {meta['count']}")


if __name__ == "__main__":
    main()
