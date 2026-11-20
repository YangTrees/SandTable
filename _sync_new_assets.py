# -*- coding: utf-8 -*-
"""Sync the 100 newly generated sandplay images from the agent trajectory."""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DICT_PATH = ROOT / "assets" / "sandplay_miniatures_500.json"
GEN = ROOT / "assets" / "generated"
WHITE = GEN / "white"
URL_MAP = GEN / "url_map.json"
REPORT = GEN / "new_asset_sync.json"

CATEGORY_CODES = {
    "攻击与对抗": "conflict_combat",
    "禁闭与学业重压": "confinement_pressure",
    "灾害与破损枯竭": "crisis_decay",
    "情绪姿态与阴影人物": "shadow_figures",
    "中性张力与转化": "neutral_transformation",
}


def safe_filename(value: str) -> str:
    value = re.sub(r"[^\w\-]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "unknown"


def latest_trajectory() -> Path:
    base = Path.home() / "AppData/Local/DoubaoWork/User Data/Default/.doubaowork/agent_mode/workspace/.sessions"
    files = sorted(base.rglob("trajectory.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise SystemExit("trajectory.jsonl not found")
    return files[0]


def main() -> int:
    payload = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    new_items = [x for x in payload["items"] if x["id"].split("_", 1)[0] in {"CONFLICT", "CONFINEMENT", "CRISIS", "SHADOW", "NEUTRAL"}]
    prompt_map = {x["prompt"]: x for x in new_items}

    trajectory = latest_trajectory()
    raw = trajectory.read_text(encoding="utf-8", errors="replace")
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

    pattern = re.compile(
        r'<generated_images prompt="([^"]*)">.*?<uri>(https://aka\.doubaocdn\.com/s/[A-Za-z0-9]+)</uri>',
        re.S,
    )
    found: dict[str, str] = {}
    unknown = 0
    for prompt, url in pattern.findall(text):
        item = prompt_map.get(prompt)
        if item is None:
            unknown += 1
            continue
        found[item["id"]] = url

    missing = [x["id"] for x in new_items if x["id"] not in found]
    print(json.dumps({"trajectory": str(trajectory), "matched": len(found), "missing": missing, "unknown_prompts": unknown}, ensure_ascii=False))

    old_map = json.loads(URL_MAP.read_text(encoding="utf-8")) if URL_MAP.exists() else {}
    old_map.update(found)
    URL_MAP.write_text(json.dumps(old_map, ensure_ascii=False, indent=1), encoding="utf-8")

    downloaded = skipped = failed = 0
    records = []
    for item in new_items:
        url = found.get(item["id"])
        if not url:
            continue
        code = CATEGORY_CODES[item["category"]]
        dest = WHITE / code / f"{safe_filename(item['id'])}_{safe_filename(item['name'])}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size > 2000:
            skipped += 1
            records.append({"id": item["id"], "name": item["name"], "status": "skipped", "path": str(dest), "url": url})
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as response:
                data = response.read()
            dest.write_bytes(data)
            downloaded += 1
            records.append({"id": item["id"], "name": item["name"], "status": "success", "path": str(dest), "url": url, "bytes": len(data)})
        except Exception as exc:  # noqa: BLE001
            failed += 1
            records.append({"id": item["id"], "name": item["name"], "status": "failed", "error": str(exc), "url": url})

    REPORT.write_text(json.dumps({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "matched": len(found), "missing": missing, "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"downloaded": downloaded, "skipped": skipped, "failed": failed, "report": str(REPORT)}, ensure_ascii=False))
    return 0 if not missing and failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
