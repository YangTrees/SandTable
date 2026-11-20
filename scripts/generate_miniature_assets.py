# -*- coding: utf-8 -*-
r"""
批量生成心理沙盘沙具白底图，并使用 rembg 自动抠成透明 PNG。

默认读取：
  D:\AI\AI_SandBox\assets\sandplay_miniatures_500.json

默认输出：
  D:\AI\AI_SandBox\assets\generated\white\<category_code>\<item_id>.png
  D:\AI\AI_SandBox\assets\generated\transparent\<category_code>\<item_id>.png
  D:\AI\AI_SandBox\assets\generated\manifest.jsonl

OpenAI-compatible Images API 示例：
  $env:IMAGE_API_KEY="你的 API Key"
  python scripts\generate_miniature_assets.py `
    --provider openai-compatible `
    --base-url "https://你的生图服务地址/v1" `
    --model "你的生图模型" `
    --size "1024x1024" `
    --limit 10 `
    --concurrency 2

本地 mock 测试（不调用 API，只测试目录、JSON、抠图流程）：
  python scripts\generate_miniature_assets.py --provider mock --limit 2 --overwrite

依赖安装：
  python -m pip install -r scripts\requirements-miniature-assets.txt
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import io
import json
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sandplay_asset_spec import (
    decontaminate,
    compose_shadows,
    fit_square,
    encode_png,
    encode_webp,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "assets" / "sandplay_miniatures_500.json"
DEFAULT_OUTPUT_ROOT = ROOT / "assets" / "generated"

CATEGORY_CODES = {
    "人物与角色原型": "person_role",
    "建筑与居所": "building_home",
    "自然山水与植物": "nature_plant",
    "动物与神兽": "animal_myth",
    "交通工具与现代器物": "vehicle_tool",
    "学习与生活道具": "study_life",
    "神秘与象征符号": "mystic_symbol",
    "饮食与丰饶意象": "food_abundance",
    "攻击与对抗": "conflict_combat",
    "禁闭与学业重压": "confinement_pressure",
    "灾害与破损枯竭": "crisis_decay",
    "情绪姿态与阴影人物": "shadow_figures",
    "中性张力与转化": "neutral_transformation",
}

MANIFEST_LOCK = threading.Lock()
_REMBG_SESSION = None
_REMBG_SESSION_LOCK = threading.Lock()

# A few generations placed their invisible asset ID marker on the canvas.
# Crop the top strip before matting so the text never becomes a foreground speck.
WHITE_TOP_CROP = {
    "FOOD_006": 90,
    "MYSTIC_036": 90,
    "MYSTIC_007": 90,
    "VEHICLE_008": 90,
}


@dataclass(frozen=True)
class MiniatureItem:
    id: str
    name: str
    category: str
    psychology_meaning: str
    prompt: str
    asset_group: str = ""

    @property
    def category_code(self) -> str:
        return self.asset_group or CATEGORY_CODES.get(self.category, safe_filename(self.category))


@dataclass
class GenerateResult:
    item_id: str
    name: str
    category_code: str
    status: str
    prompt: str
    white_path: Optional[str] = None
    transparent_path: Optional[str] = None
    transparent_webp_path: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    duration_seconds: float = 0.0


def safe_filename(value: str) -> str:
    value = re.sub(r"[^\w\-]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "unknown"


def load_items(path: Path) -> Tuple[List[MiniatureItem], Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    raw_items = payload.get("items", payload if isinstance(payload, list) else [])
    items: List[MiniatureItem] = []
    required = {"id", "name", "category", "psychology_meaning", "prompt"}

    for index, raw in enumerate(raw_items, start=1):
        missing = required - set(raw)
        if missing:
            raise ValueError(f"第 {index} 个沙具缺少字段: {sorted(missing)}")
        items.append(
            MiniatureItem(
                id=str(raw["id"]),
                name=str(raw["name"]),
                category=str(raw["category"]),
                psychology_meaning=str(raw["psychology_meaning"]),
                prompt=str(raw["prompt"]),
                asset_group=str(raw.get("asset_group", "")),
            )
        )
    return items, payload


def filter_items(items: List[MiniatureItem], args: argparse.Namespace) -> List[MiniatureItem]:
    filtered = items

    if args.category:
        allowed = {x.strip() for x in args.category.split(",") if x.strip()}
        filtered = [
            item for item in filtered
            if item.category in allowed or item.category_code in allowed
        ]

    if args.ids:
        allowed_ids = {x.strip() for x in args.ids.split(",") if x.strip()}
        filtered = [item for item in filtered if item.id in allowed_ids]

    if args.start > 0:
        filtered = filtered[args.start:]

    if args.limit is not None:
        filtered = filtered[:args.limit]

    return filtered


def ensure_dirs(output_root: Path) -> Dict[str, Path]:
    paths = {
        "white": output_root / "white",
        "transparent": output_root / "transparent",
        "manifest": output_root / "manifest.jsonl",
    }
    paths["white"].mkdir(parents=True, exist_ok=True)
    paths["transparent"].mkdir(parents=True, exist_ok=True)
    return paths


def target_paths(output_root: Path, item: MiniatureItem) -> Tuple[Path, Path, Path]:
    filename = f"{safe_filename(item.id)}_{safe_filename(item.name)}.png"
    white_path = output_root / "white" / item.category_code / filename
    transparent_path = output_root / "transparent" / item.category_code / filename
    transparent_webp_path = transparent_path.with_suffix(".webp")
    white_path.parent.mkdir(parents=True, exist_ok=True)
    transparent_path.parent.mkdir(parents=True, exist_ok=True)
    return white_path, transparent_path, transparent_webp_path


def should_skip(
    white_path: Path,
    transparent_path: Path,
    transparent_webp_path: Path,
    overwrite: bool,
) -> bool:
    return (
        not overwrite
        and white_path.exists()
        and transparent_path.exists()
        and transparent_webp_path.exists()
        and white_path.stat().st_size > 0
        and transparent_path.stat().st_size > 0
        and transparent_webp_path.stat().st_size > 0
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_mock_image(item: MiniatureItem, size: Tuple[int, int]) -> bytes:
    """生成本地 mock 白底图，用于无 API Key 时测试 rembg 流程。"""
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("缺少 Pillow，请先执行：python -m pip install Pillow") from exc

    width, height = size
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    seed = int(hashlib.sha256(item.id.encode("utf-8")).hexdigest()[:8], 16)
    random.seed(seed)

    color = (
        80 + random.randint(0, 120),
        80 + random.randint(0, 120),
        80 + random.randint(0, 120),
    )
    center_x, center_y = width // 2, height // 2
    box_w, box_h = width // 3, height // 3
    box = (
        center_x - box_w // 2,
        center_y - box_h // 2,
        center_x + box_w // 2,
        center_y + box_h // 2,
    )
    draw.rounded_rectangle(box, radius=min(width, height) // 12, fill=color, outline=(60, 60, 60), width=3)
    draw.ellipse((box[0] + 20, box[1] + 20, box[0] + 90, box[1] + 90), fill=(245, 220, 170))

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def http_json_request(
    url: str,
    payload: Dict[str, Any],
    api_key: str,
    timeout: int,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if extra_headers:
        headers.update(extra_headers)

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"生图 API HTTP {exc.code}: {detail[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"生图 API 网络错误: {exc}") from exc


def download_bytes(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "sandplay-miniature-generator/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except Exception as exc:
        raise RuntimeError(f"下载生成图失败: {exc}") from exc


def extract_image_bytes(response: Dict[str, Any], timeout: int) -> bytes:
    """兼容常见 Images API 返回：b64_json、url、image_url。"""
    data = response.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            if first.get("b64_json"):
                return base64.b64decode(first["b64_json"])
            if first.get("url"):
                return download_bytes(str(first["url"]), timeout)
            if first.get("image_url"):
                return download_bytes(str(first["image_url"]), timeout)

    # 部分服务直接返回 output 或 result
    for key in ("output", "result"):
        value = response.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return download_bytes(value, timeout)
        if isinstance(value, dict):
            if value.get("b64_json"):
                return base64.b64decode(value["b64_json"])
            if value.get("url"):
                return download_bytes(str(value["url"]), timeout)

    raise RuntimeError(f"无法从生图 API 响应中解析图片: {json.dumps(response, ensure_ascii=False)[:1000]}")


def parse_size(size_text: str) -> Tuple[int, int]:
    match = re.fullmatch(r"(\d+)x(\d+)", size_text.strip().lower())
    if not match:
        raise argparse.ArgumentTypeError("--size 格式必须类似 1024x1024")
    width, height = int(match.group(1)), int(match.group(2))
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("--size 宽高必须为正整数")
    return width, height


def generate_white_image(item: MiniatureItem, args: argparse.Namespace) -> bytes:
    if args.provider == "mock":
        return make_mock_image(item, args.size)

    if args.provider == "local":
        white_path, _, _ = target_paths(args.output_root, item)
        if not white_path.exists():
            raise RuntimeError(f"本地白底图不存在: {white_path}")
        return white_path.read_bytes()

    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"缺少 API Key：请设置环境变量 {args.api_key_env}")

    base_url = args.base_url.rstrip("/")
    endpoint = f"{base_url}/images/generations"
    payload: Dict[str, Any] = {
        "model": args.model,
        "prompt": item.prompt,
        "size": f"{args.size[0]}x{args.size[1]}",
        "n": 1,
    }

    if args.extra_body_json:
        extra = json.loads(args.extra_body_json)
        if not isinstance(extra, dict):
            raise ValueError("--extra-body-json 必须是 JSON 对象")
        payload.update(extra)

    response = http_json_request(
        endpoint,
        payload=payload,
        api_key=api_key,
        timeout=args.timeout,
        extra_headers=json.loads(args.extra_headers_json) if args.extra_headers_json else None,
    )
    return extract_image_bytes(response, timeout=args.timeout)


def get_rembg_session():
    global _REMBG_SESSION
    if _REMBG_SESSION is None:
        with _REMBG_SESSION_LOCK:
            if _REMBG_SESSION is None:
                from rembg import new_session

                _REMBG_SESSION = new_session("u2net")
    return _REMBG_SESSION


def remove_background(
    white_bytes: bytes,
    trim: bool,
    trim_padding: int,
    asset_size: int = 512,
) -> Tuple[bytes, bytes]:
    """Create a square 512 PNG and a WebP from one white-background image.

    The foreground is produced with rembg alpha matting, decontaminated from
    the white studio background, and grounded with a preserved contact shadow.
    ``trim`` and ``trim_padding`` remain accepted for CLI compatibility; the
    final asset is always a centered square canvas.
    """
    try:
        from PIL import Image
        from rembg import remove
    except ImportError as exc:
        raise RuntimeError(
            "缺少 Pillow 或 rembg，请先执行：python -m pip install -r scripts\\requirements-miniature-assets.txt"
        ) from exc

    source = Image.open(io.BytesIO(white_bytes)).convert("RGB")
    raw_bytes = remove(
        white_bytes,
        session=get_rembg_session(),
        alpha_matting=True,
        alpha_matting_foreground_threshold=240,
        alpha_matting_background_threshold=10,
        alpha_matting_erode_size=6,
    )
    raw = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    clean = decontaminate(source, raw)

    final = Image.new("RGBA", clean.size, (0, 0, 0, 0))
    final.alpha_composite(compose_shadows(source, clean))
    final.alpha_composite(clean)
    asset = fit_square(final, size=asset_size, margin=0.06)

    return encode_png(asset), encode_webp(asset)


def write_manifest(path: Path, result: GenerateResult) -> None:
    png_bytes = Path(result.transparent_path).stat().st_size if result.transparent_path and Path(result.transparent_path).exists() else None
    webp_bytes = Path(result.transparent_webp_path).stat().st_size if result.transparent_webp_path and Path(result.transparent_webp_path).exists() else None
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "id": result.item_id,
        "name": result.name,
        "category_code": result.category_code,
        "status": result.status,
        "white_path": result.white_path,
        "transparent_path": result.transparent_path,
        "transparent_webp_path": result.transparent_webp_path,
        "asset_width": 512,
        "asset_height": 512,
        "transparent_png_bytes": png_bytes,
        "transparent_webp_bytes": webp_bytes,
        "error": result.error,
        "attempts": result.attempts,
        "duration_seconds": round(result.duration_seconds, 3),
        "prompt_sha256": sha256_bytes(result.prompt.encode("utf-8")),
    }
    with MANIFEST_LOCK:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def process_item(item: MiniatureItem, args: argparse.Namespace, output_root: Path) -> GenerateResult:
    started = time.time()
    white_path, transparent_path, transparent_webp_path = target_paths(output_root, item)
    result = GenerateResult(
        item_id=item.id,
        name=item.name,
        category_code=item.category_code,
        status="pending",
        prompt=item.prompt,
    )

    if should_skip(white_path, transparent_path, transparent_webp_path, args.overwrite):
        result.status = "skipped"
        result.white_path = str(white_path)
        result.transparent_path = str(transparent_path)
        result.transparent_webp_path = str(transparent_webp_path)
        result.duration_seconds = time.time() - started
        return result

    if args.dry_run:
        result.status = "dry_run"
        result.white_path = str(white_path)
        result.transparent_path = str(transparent_path)
        result.transparent_webp_path = str(transparent_webp_path)
        result.duration_seconds = time.time() - started
        return result

    last_error: Optional[Exception] = None
    for attempt in range(1, args.retries + 2):
        result.attempts = attempt
        try:
            white_bytes = generate_white_image(item, args)
            crop_top = WHITE_TOP_CROP.get(item.id)
            if crop_top:
                try:
                    from PIL import Image
                    image = Image.open(io.BytesIO(white_bytes)).convert("RGB")
                    image = image.crop((0, min(crop_top, image.height - 1), image.width, image.height))
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG")
                    white_bytes = buffer.getvalue()
                except ImportError as exc:
                    raise RuntimeError("缺少 Pillow，无法清理画布标记") from exc
            white_path.write_bytes(white_bytes)

            transparent_bytes, webp_bytes = remove_background(
                white_bytes,
                trim=not args.no_trim,
                trim_padding=args.trim_padding,
                asset_size=args.asset_size,
            )
            transparent_path.write_bytes(transparent_bytes)
            transparent_webp_path.write_bytes(webp_bytes)

            result.status = "success"
            result.white_path = str(white_path)
            result.transparent_path = str(transparent_path)
            result.transparent_webp_path = str(transparent_webp_path)
            result.duration_seconds = time.time() - started
            return result
        except Exception as exc:  # noqa: BLE001 - CLI 需要汇总所有失败原因
            last_error = exc
            if attempt <= args.retries:
                sleep_seconds = min(args.retry_backoff * (2 ** (attempt - 1)), args.retry_backoff_max)
                time.sleep(sleep_seconds + random.uniform(0, 0.5))

    result.status = "failed"
    result.error = str(last_error) if last_error else "unknown error"
    result.duration_seconds = time.time() - started
    return result


def summarize(results: Iterable[GenerateResult]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for result in results:
        summary[result.status] = summary.get(result.status, 0) + 1
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="批量生成 500 个心理沙盘沙具白底图，并用 rembg 输出透明 PNG。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="沙具 JSON 文件路径")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help="生成图输出根目录")
    parser.add_argument("--provider", choices=["openai-compatible", "mock", "local"], default="openai-compatible", help="生图服务类型；local 直接读取已下载的白底图并抠图")
    parser.add_argument("--base-url", default=os.environ.get("IMAGE_API_BASE_URL", ""), help="OpenAI-compatible API Base URL，例如 https://xxx/v1")
    parser.add_argument("--model", default=os.environ.get("IMAGE_MODEL", ""), help="生图模型名称")
    parser.add_argument("--api-key-env", default="IMAGE_API_KEY", help="API Key 环境变量名")
    parser.add_argument("--size", type=parse_size, default=parse_size("1024x1024"), help="生图请求尺寸，格式 宽x高")
    parser.add_argument("--asset-size", type=int, default=512, help="透明资产画布边长，默认 512x512")
    parser.add_argument("--limit", type=int, default=None, help="最多处理多少个沙具")
    parser.add_argument("--start", type=int, default=0, help="从第 N 个后开始，0 表示从头开始")
    parser.add_argument("--category", default=None, help="按分类过滤，支持中文分类名或英文 code，多个用英文逗号分隔")
    parser.add_argument("--ids", default=None, help="按沙具 ID 过滤，多个用英文逗号分隔")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在图片")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要处理的任务，不调用 API、不写图片")
    parser.add_argument("--concurrency", type=int, default=2, help="并发数")
    parser.add_argument("--request-delay", type=float, default=0.2, help="每个任务完成后的基础间隔秒数")
    parser.add_argument("--timeout", type=int, default=180, help="单次 HTTP 请求超时秒数")
    parser.add_argument("--retries", type=int, default=2, help="失败重试次数")
    parser.add_argument("--retry-backoff", type=float, default=2.0, help="指数退避初始秒数")
    parser.add_argument("--retry-backoff-max", type=float, default=20.0, help="指数退避最大秒数")
    parser.add_argument("--extra-body-json", default=None, help="附加到生图 API 请求体的 JSON 对象字符串")
    parser.add_argument("--extra-headers-json", default=None, help="附加到生图 API 请求头的 JSON 对象字符串")
    parser.add_argument("--no-trim", action="store_true", help="保留抠图后的透明边距，不自动裁剪")
    parser.add_argument("--trim-padding", type=int, default=16, help="自动裁剪透明边距时保留的像素边距")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.concurrency < 1:
        raise ValueError("--concurrency 必须 >= 1")
    if args.asset_size < 64:
        raise ValueError("--asset-size 必须 >= 64")
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit 必须 >= 1")
    if args.start < 0:
        raise ValueError("--start 必须 >= 0")
    if args.retries < 0:
        raise ValueError("--retries 必须 >= 0")
    if args.trim_padding < 0:
        raise ValueError("--trim-padding 必须 >= 0")
    if args.provider == "openai-compatible" and not args.dry_run:
        if not args.base_url:
            raise ValueError("provider=openai-compatible 时必须提供 --base-url 或 IMAGE_API_BASE_URL")
        if not args.model:
            raise ValueError("provider=openai-compatible 时必须提供 --model 或 IMAGE_MODEL")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        validate_args(args)
        items, payload = load_items(args.input)
        selected = filter_items(items, args)
        ensure_dirs(args.output_root)
        manifest_path = args.output_root / "manifest.jsonl"

        print(f"输入文件: {args.input}")
        print(f"总沙具数: {len(items)}，本次选中: {len(selected)}")
        print(f"输出目录: {args.output_root}")
        print(f"模式: {'dry-run' if args.dry_run else args.provider}")

        if not selected:
            print("没有匹配的沙具。")
            return 0

        results: List[GenerateResult] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            future_map = {
                executor.submit(process_item, item, args, args.output_root): item
                for item in selected
            }
            for index, future in enumerate(concurrent.futures.as_completed(future_map), start=1):
                item = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001
                    result = GenerateResult(
                        item_id=item.id,
                        name=item.name,
                        category_code=item.category_code,
                        status="failed",
                        prompt=item.prompt,
                        error=str(exc),
                    )
                results.append(result)
                write_manifest(manifest_path, result)
                print(f"[{index}/{len(selected)}] {result.status:8s} {item.id} {item.name} {result.error or ''}")
                time.sleep(args.request_delay)

        summary = summarize(results)
        print("执行汇总:", json.dumps(summary, ensure_ascii=False, sort_keys=True))
        print(f"Manifest: {manifest_path}")
        return 0 if summary.get("failed", 0) == 0 else 1

    except Exception as exc:  # noqa: BLE001
        print(f"执行失败: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
