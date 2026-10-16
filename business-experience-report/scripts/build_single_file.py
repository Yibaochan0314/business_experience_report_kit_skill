#!/usr/bin/env python3
"""build_single_file.py -- 把报告源 HTML 里的相对路径图片内联为 base64，产出单文件成品。

用法:
    # 预演：只统计会内联哪些图、总体积多大，不写文件
    python build_single_file.py --src report.src.html --dry-run

    # 正式生成
    python build_single_file.py --src report.src.html --out "产品名-业务体验分析报告.html"

    # 体积超限时给出压缩建议
    python build_single_file.py --src report.src.html --max-mb 3

要点:
    - 只内联「相对路径且文件真实存在」的图片，外链 http(s) 图片保持原样
    - 已内联的 data: URI 会跳过，可重复执行
    - 输出前做体积检查，超限给出可执行的压缩命令

不要手写 base64 —— 用这个脚本。
"""

from __future__ import annotations

import argparse
import base64
import mimetypes
import os
import re
import sys
from pathlib import Path

MIME_FALLBACK = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}

# 匹配 src="..." / src='...'，忽略已是 data: 或 http(s) 的引用
SRC_RE = re.compile(r"""src\s*=\s*(["'])(?P<url>[^"']+)\1""", re.IGNORECASE)


def guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or MIME_FALLBACK.get(path.suffix.lower(), "application/octet-stream")


def is_inlinable(url: str) -> bool:
    if url.startswith(("data:", "http://", "https://", "//", "#")):
        return False
    return True


def build(src: Path, out: Path | None, max_mb: float, dry_run: bool) -> int:
    if not src.exists():
        print(f"[ERROR] 源文件不存在: {src}", file=sys.stderr)
        return 1

    html = src.read_text(encoding="utf-8")
    base_dir = src.parent

    inlined: list[tuple[str, int, int]] = []  # (path, raw_bytes, b64_chars)
    missing: list[str] = []

    def repl(m: re.Match[str]) -> str:
        url = m.group("url")
        if not is_inlinable(url):
            return m.group(0)
        # 去掉可能的查询串
        clean = url.split("?", 1)[0].split("#", 1)[0]
        f = (base_dir / clean) if not os.path.isabs(clean) else Path(clean)
        if not f.exists():
            missing.append(url)
            return m.group(0)
        raw = f.read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        inlined.append((clean, len(raw), len(b64)))
        return f'src="data:{guess_mime(f)};base64,{b64}"'

    new_html = SRC_RE.sub(repl, html)

    print("=" * 62)
    print(f"源文件        : {src}  ({src.stat().st_size / 1024:.1f} KB)")
    print(f"命中可内联图片: {len(inlined)} 张")
    for p, raw, b64 in inlined:
        print(f"  - {p:<44} 原始 {raw / 1024:7.1f} KB -> base64 {b64 / 1024:7.1f} KB")
    if missing:
        print(f"[WARN] 以下 src 指向的文件不存在，已保持原样（{len(missing)} 个）:")
        for m in missing:
            print(f"  ! {m}")

    if dry_run:
        total_b64 = sum(b for _, _, b in inlined)
        print("-" * 62)
        print(f"[DRY-RUN] 预计成品体积: {(len(new_html.encode('utf-8')) + total_b64) / 1024 / 1024:.2f} MB")
        return 0

    if out is None:
        stem = src.stem.replace(".src", "")
        out = src.with_name(f"{stem}.html")

    out.write_text(new_html, encoding="utf-8")
    size_mb = out.stat().st_size / 1024 / 1024

    print("-" * 62)
    print(f"输出          : {out}")
    print(f"输出体积      : {size_mb:.2f} MB  ({out.stat().st_size / 1024:.0f} KB)")

    if size_mb > max_mb:
        print()
        print(f"[WARN] 超过 {max_mb} MB 上限。压缩建议：")
        print("  # 重新压缩（宽度 1000 / JPEG 质量 72，通常可减半）")
        print('  for f in shots/w*.jpg; do')
        print('    sips -s format jpeg -s formatOptions 72 --resampleWidth 1000 "$f" --out "$f"')
        print('  done')
        print("  # 或降低质量到 55 / 宽度到 820，或减少嵌入张数（优先保能推翻结论的图）")
        return 2

    print("[OK] 单文件生成完成，可直接双击打开与分享。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="把报告 HTML 的相对路径图片内联为 base64 单文件")
    ap.add_argument("--src", default="report.src.html", help="源 HTML（默认 report.src.html）")
    ap.add_argument("--out", default=None, help="输出 HTML（默认由源文件名推导）")
    ap.add_argument("--max-mb", type=float, default=3.0, help="体积上限 MB（默认 3.0）")
    ap.add_argument("--dry-run", action="store_true", help="只预演统计，不写文件")
    args = ap.parse_args()

    return build(Path(args.src), Path(args.out) if args.out else None, args.max_mb, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
