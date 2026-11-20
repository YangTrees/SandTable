#!/usr/bin/env python3
"""Sync generated white-background sandplay images from the agent trajectory.

Each image prompt carries an `Asset ID: <id>` marker, so URLs returned by the
image tool can be mapped back to the 500-item dictionary without manual copying.
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "assets" / "generated"
WHITE = GEN / "white"
TRAJECTORY = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else None
if TRAJECTORY is None:
    # Standard session trace location, relative to this project.
    cand = sorted((Path.home() / "AppData/Local/DoubaoWork/User Data/Default"
                   / ".doubaowork/agent_mode/workspace/.sessions").glob(
        "*/agents/*/system/trajectory.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    TRAJECTORY = cand[0] if cand else None

if not TRAJECTORY or not TRAJECTORY.exists():
    raise SystemExit("trajectory.jsonl not found; pass the path as argv[1]")

raw = TRAJECTORY.read_text(encoding="utf-8", errors="replace")
# trajectory.jsonl stores the tool content as an escaped JSON string; decode each
# record first so prompt="..." is visible to the regex.
chunks = []
for line in raw.splitlines():
    try:
        obj = json.loads(line)
        content = obj.get("content")
        if isinstance(content, str):
            chunks.append(content)
    except Exception:
        pass
text = "\n".join(chunks) if chunks else raw.replace('\\"', '"')
# The result has prompt="..." and <uri>...</uri> in the same generated_images block.
pat = re.compile(
    r'<generated_images prompt="([^"]*)">.*?<uri>(https://aka\.doubaocdn\.com/s/[A-Za-z0-9]+)</uri>',
    re.S,
)
records = {}
for prompt, url in pat.findall(text):
    m = re.search(r"Asset ID:\s*([A-Z]+_[0-9]{3})", prompt)
    if not m:
        continue
    aid = m.group(1)
    records[aid] = url

# Read the final dictionary so filenames remain stable and human-readable.
items = json.loads((ROOT / "assets" / "sandplay_miniatures_500.json").read_text(encoding="utf-8"))["items"]
meta = {x["id"]: x for x in items}
urls = {aid: url for aid, url in records.items() if aid in meta}
(GEN / "url_map.json").write_text(json.dumps(urls, ensure_ascii=False, indent=1), encoding="utf-8")

CATEGORY_CODES = {
    "人物与角色原型": "person_role",
    "建筑与居所": "building_home",
    "自然山水与植物": "nature_plant",
    "动物与神兽": "animal_myth",
    "交通工具与现代器物": "vehicle_tool",
    "学习与生活道具": "study_life",
    "神秘与象征符号": "mystic_symbol",
    "饮食与丰饶意象": "food_abundance",
}

WHITE.mkdir(parents=True, exist_ok=True)
ok = fail = skip = 0
for aid, url in urls.items():
    x = meta[aid]
    code = CATEGORY_CODES.get(x["category"], aid.split("_", 1)[0].lower())
    dest = WHITE / code / f"{aid}_{x['name']}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        skip += 1
        continue
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                dest.write_bytes(r.read())
            ok += 1
            break
        except Exception as e:
            if attempt == 2:
                print("FAIL", aid, url, e)
                fail += 1
            time.sleep(1)
print(json.dumps({"mapped": len(urls), "downloaded": ok, "skip": skip, "failed": fail, "white_dir": str(WHITE)}, ensure_ascii=False))
