# -*- coding: utf-8 -*-
"""Generate white-background art for the 100 newly appended sandplay items.

Reads the master dictionary, calls the Ark Images API with the exact prompt
stored on each item, and saves a PNG under assets/generated/white/<category>/.
No prompt rewriting and no text markers are added.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DICT_PATH = ROOT / "assets" / "sandplay_miniatures_500.json"
ENV_PATH = ROOT / "backend" / ".env"
GEN_ROOT = ROOT / "assets" / "generated"
WHITE_ROOT = GEN_ROOT / "white"
NEW_MANIFEST = GEN_ROOT / "new_asset_generation.jsonl"

CATEGORY_CODES = {
    "攻击与对抗": "conflict_combat",
    "禁闭与学业重压": "confinement_pressure",
    "灾害与破损枯竭": "crisis_decay",
    "情绪姿态与阴影人物": "shadow_figures",
    "中性张力与转化": "neutral_transformation",
}


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def safe_filename(value: str) -> str:
    value = re.sub(r"[^\w\-]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "unknown"


def load_items() -> list[dict[str, Any]]:
    payload = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    return [x for x in payload["items"] if x["id"].split("_", 1)[0] in {"CONFLICT", "CONFINEMENT", "CRISIS", "SHADOW", "NEUTRAL"}]


def target_path(item: dict[str, Any]) -> Path:
    code = CATEGORY_CODES[item["category"]]
    return WHITE_ROOT / code / f"{safe_filename(item['id'])}_{safe_filename(item['name'])}.png"


def download(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "sandplay-asset-generator/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def generate_one(item: dict[str, Any], api_key: str, base_url: str, model: str, size: str, overwrite: bool, retries: int) -> dict[str, Any]:
    dest = target_path(item)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 2000 and not overwrite:
        return {"id": item["id"], "name": item["name"], "status": "skipped", "path": str(dest)}

    endpoint = base_url.rstrip("/") + "/images/generations"
    payload = {
        "model": model,
        "prompt": item["prompt"],
        "size": size,
        "response_format": "url",
        "output_format": "png",
        "watermark": False,
        "sequential_image_generation": "disabled",
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error = ""
    for attempt in range(1, retries + 2):
        try:
            req = urllib.request.Request(
                endpoint,
                data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=300) as response:
                result = json.loads(response.read().decode("utf-8"))
            data = result.get("data") or []
            if not data:
                code = result.get("error", {}).get("code") or result.get("code") or "no_data"
                message = result.get("error", {}).get("message") or result.get("message") or ""
                raise RuntimeError(f"{code}: {message}")
            first = data[0]
            url = first.get("url") or first.get("image_url")
            if url:
                raw = download(str(url))
            elif first.get("b64_json"):
                import base64
                raw = base64.b64decode(first["b64_json"])
            else:
                raise RuntimeError("response has neither url nor b64_json")
            dest.write_bytes(raw)
            return {
                "id": item["id"], "name": item["name"], "status": "success", "path": str(dest),
                "bytes": len(raw), "attempt": attempt, "remote_size": first.get("size"),
            }
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt <= retries:
                time.sleep(min(60, 3 * (2 ** (attempt - 1))))
    return {"id": item["id"], "name": item["name"], "status": "failed", "error": last_error}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", default="")
    parser.add_argument("--category", default="")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--model", default="doubao-seedream-5-5-261028")
    parser.add_argument("--size", default="2048x2048")
    args = parser.parse_args()

    env = load_env(ENV_PATH)
    api_key = env.get("MULTIMODAL_API_KEY", "").strip()
    base_url = env.get("MULTIMODAL_BASE_URL", "").strip()
    if not api_key or not base_url:
        raise SystemExit("backend/.env 缺少 MULTIMODAL_API_KEY 或 MULTIMODAL_BASE_URL")

    items = load_items()
    if args.ids:
        allowed = {x.strip() for x in args.ids.split(",") if x.strip()}
        items = [x for x in items if x["id"] in allowed]
    if args.category:
        allowed_categories = {x.strip() for x in args.category.split(",") if x.strip()}
        items = [x for x in items if x["category"] in allowed_categories or CATEGORY_CODES.get(x["category"]) in allowed_categories]
    if args.limit is not None:
        items = items[: args.limit]

    print(f"selected={len(items)} model={args.model} size={args.size}")
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = {
            pool.submit(generate_one, item, api_key, base_url, args.model, args.size, args.overwrite, args.retries): item
            for item in items
        }
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            item = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                result = {"id": item["id"], "name": item["name"], "status": "failed", "error": str(exc)}
            results.append(result)
            with NEW_MANIFEST.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({**result, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, ensure_ascii=False) + "\n")
            print(f"[{index}/{len(items)}] {result['status']} {result['id']} {result['name']} {result.get('error', '')}")

    summary: dict[str, int] = {}
    for result in results:
        summary[result["status"]] = summary.get(result["status"], 0) + 1
    print("summary", json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary.get("failed", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
