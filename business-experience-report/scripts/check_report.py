#!/usr/bin/env python3
"""check_report.py -- 业务体验分析报告交付自检

对 report.src.html（或成品 HTML）做结构与合规检查，可选对导出的 PDF 做页数/
空白页/体积检查。输出分级结果：PASS / WARN / FAIL。

用法:
    python check_report.py --src report.src.html
    python check_report.py --src report.src.html --pdf "产品名-业务体验分析报告.pdf"
    python check_report.py --src report.src.html --json      # 机读输出

退出码: 0 = 无 FAIL；1 = 存在 FAIL。

修复记录（2026-10-16）：
  1. 内容型检查（CHECKS / FORBIDDEN）此前直接正则扫全文，未剥离 data URI 的 base64
     载荷。base64 字符集含 X/A 等字母，`XXX`（placeholder_pending）在约 1MB 内联
     图片中必然随机命中数次 → 单文件成品恒定误报 FAIL；更隐蔽的是短模式（如
     `5A`）在 base64 中平均每 4096 字符命中一次，导致对应检查「永远通过」、检测力
     归零。现改为先 sanitize 掉 base64 载荷（保留 `data:image/...;base64,` 前缀，
     不影响内联计数）再做全部内容型检查，并在结果中报告剥离块数以便核对。
  2. 新增底部留白检查（pdf_gap，可选，需 pypdfium2）：逐页渲染统计内容底界，底部
     空档 > 70% 报 WARN。CSS 的 break-inside:avoid 是「全有或全无」，不可分割块大于
     剩余空间时只能整块下移，必然在上一页尾部留白——这类「零头孤页」过去只能靠
     人眼发现，且不会被 pdf_blank 捕获（它们并非无内容，只是几乎为空）。
     pypdfium2 缺失时该项自动跳过，不报错。
  （注：pdf_blank 的「整页截图页误判」修正由 skill 更新版自带，见 _page_has_visual。）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# (key, 级别, 人类可读说明, 任一命中即通过的正则列表)
CHECKS: list[tuple[str, str, str, list[str]]] = [
    ("cover", "FAIL", "封面 Hero 存在且含标题", [r'class="hero"', r"<h1[^>]*>"]),
    ("cover_question", "WARN", "封面副标题包含被回答的业务问题", [r'class="sub"']),
    ("kpi", "WARN", "关键数字卡 >= 4 张", [r'class="kpi"']),
    ("nav", "WARN", "阅读导航（三章）", [r'class="nav"']),
    ("summary", "WARN", "摘要：一句话结论", [r"摘要"]),
    ("ch1", "FAIL", "第一章 业务背景", [r'id="ch1"']),
    ("ch1_company", "FAIL", "1.1 公司背景与产品定位", [r"公司背景"]),
    ("ch1_industry", "FAIL", "1.2 行业背景与目标用户画像", [r"行业背景", r"用户画像"]),
    ("ch2", "FAIL", "第二章 业务诊断", [r'id="ch2"']),
    ("ch2_flow", "FAIL", "2.1 业务流程与核心路径体验", [r"核心路径", r"业务流程"]),
    ("ch2_pricing", "WARN", "2.1 含定价与策略", [r"定价"]),
    ("ch2_channel", "WARN", "2.1 含获客渠道", [r"获客渠道", r"渠道"]),
    ("ch2_ops", "WARN", "2.1 含现有运营手段", [r"运营手段"]),
    ("ch2_proscons", "FAIL", "2.1 亮点 / 不足双栏", [r'class="pm"', r"亮点"]),
    ("ch2_root", "FAIL", "2.2 根因分析", [r"根因"]),
    ("ch2_funnel", "FAIL", "2.2 激活漏斗图示", [r"漏斗"]),
    ("ch2_activation_std", "FAIL", "2.2 激活标准定义", [r"激活标准", r"激活定义"]),
    ("ch2_drilldown", "WARN", "2.2 多维下钻（行为×来源）", [r"下钻", r"分层"]),
    ("ch2_conclusion", "FAIL", "2.2 结论句（谁·哪环·因何）", [r"因何", r"在.*环节.*流失"]),
    ("prio_tags", "FAIL", "根因分级标签 P0/P1/P2", [r"t-p0", r"P0"]),
    ("ch3", "FAIL", "第三章 业务解决方案", [r'id="ch3"']),
    ("ch3_metrics", "FAIL", "3.1 关键指标体系", [r"指标体系", r"北极星"]),
    ("ch3_phases", "FAIL", "3.2 三阶段方案卡（3/6/12 月）", [r'class="phase"', r"12\s*个月", r"12\s*月"]),
    ("ch3_milestone", "FAIL", "每阶段含里程碑", [r"里程碑"]),
    ("ch3_dept", "WARN", "每阶段含配合部门", [r"配合部门", r"参与部门"]),
    ("ch3_resource", "WARN", "每阶段含资源投入", [r"资源投入", r"预算"]),
    ("ch3_nongoals", "WARN", "写明了 Non-goals（本阶段不做什么）", [r"不做什么", r"Non-goals", r"非目标"]),
    ("ch3_validate", "FAIL", "3.3 方案有效性验证方法", [r"验证"]),
    ("ch3_monitor", "WARN", "3.3 指标监测体系示例图", [r"监测体系", r"看板"]),
    ("ch3_raci", "WARN", "3.3 落地路径与 RACI", [r"RACI"]),
    ("method_aarrr", "FAIL", "AARRR 方法论映射", [r"AARRR"]),
    ("method_rfm", "WARN", "RFM 分层", [r"RFM"]),
    ("method_clm", "WARN", "CLM 用户生命周期", [r"CLM"]),
    ("method_5a", "WARN", "5A 模型", [r"5A"]),
    ("appendix_a", "FAIL", "附录 A 信息来源与数据口径", [r"附录\s*A", r"信息来源", r"数据口径"]),
    ("sources_url", "FAIL", "有带 URL 的来源列表", [r"https?://"]),
]

FORBIDDEN = [
    ("placeholder_todo", r"\[TODO"),
    ("placeholder_append", r"APPEND-MARK"),
    ("placeholder_pending", r"待补充内容|XXX|xxx占位"),
    ("credential_leak", r"(?i)password\s*[:=]\s*\S|密码\s*[:：]\s*\S"),
    ("unmarked_estimate", r"(?<![（(])预估\s*\d"),
]

# data URI 的 base64 载荷：只剥离载荷、保留 `data:image/png;base64,` 前缀，
# 这样内联图片计数（data:image/）不受影响，而随机字符不再污染内容型检查。
_DATA_URI_PAYLOAD = re.compile(
    r"(data:[a-z0-9.+-]+/[a-z0-9.+-]+;base64,)[A-Za-z0-9+/=\s]+",
    re.IGNORECASE,
)


def sanitize_payloads(text: str) -> tuple[str, int]:
    """剥离 data URI 的 base64 载荷，返回 (净化后文本, 剥离的载荷块数)。"""
    return _DATA_URI_PAYLOAD.subn(r"\1", text)


def check_html(raw: str) -> list[dict]:
    results: list[dict] = []

    # 内容型检查一律在净化后的文本上做（见文件头修复记录 1）
    text, stripped_blocks = sanitize_payloads(raw)

    for key, level, label, patterns in CHECKS:
        hit = any(re.search(p, text) for p in patterns)
        results.append({
            "key": key,
            "level": level if not hit else "PASS",
            "check": label,
            "hit": hit,
        })

    # 计数型检查
    def count(pattern: str) -> int:
        return len(re.findall(pattern, text))

    n_kpi = count(r'class="kpi"')
    n_phase = count(r'class="phase"')
    n_evi = count(r'class="evi"')
    n_diagram = count(r'class="diagram"')
    n_table = count(r"<table")
    n_img = count(r"<img")
    n_inline = count(r"data:image/")
    n_src_rel = len(re.findall(r'src="(?!data:|https?:|//)([^"]+\.(?:jpg|jpeg|png|webp))"', text))

    results.append({"key": "phase_count", "level": "PASS" if n_phase >= 3 else "FAIL",
                    "check": f"三阶段卡数量（{n_phase}，需 >=3）", "hit": n_phase >= 3})
    results.append({"key": "kpi_count", "level": "PASS" if n_kpi >= 4 else "WARN",
                    "check": f"关键数字卡数量（{n_kpi}，需 >=4）", "hit": n_kpi >= 4})
    results.append({"key": "diagram_count", "level": "PASS" if n_diagram >= 3 else "WARN",
                    "check": f"图示数量（{n_diagram}，建议 >=3：流转图/漏斗/指标树/监测体系）", "hit": n_diagram >= 3})
    results.append({"key": "table_count", "level": "PASS" if n_table >= 5 else "WARN",
                    "check": f"表格数量（{n_table}，建议 >=5）", "hit": n_table >= 5})
    results.append({"key": "evidence_groups", "level": "PASS" if n_evi >= 3 else "WARN",
                    "check": f"证据组数量（{n_evi}，建议 4-6 组）", "hit": n_evi >= 3})

    # 推演数据必须标注
    has_est = bool(re.search(r"推演", text))
    results.append({"key": "estimate_marked", "level": "PASS" if has_est else "WARN",
                    "check": "推演数据已显式标注（含「推演」字样）", "hit": has_est})

    # 图片内联状态
    results.append({"key": "images", "level": "PASS" if n_img == 0 or n_inline >= n_img else "WARN",
                    "check": f"图片 {n_img} 张，已内联 {n_inline} 张，仍走相对路径 {n_src_rel} 张",
                    "hit": n_img == 0 or n_inline >= n_img})

    for key, pattern in FORBIDDEN:
        m = re.search(pattern, text)
        results.append({
            "key": key,
            "level": "PASS" if not m else "FAIL",
            "check": f"无违规内容：{key}" + (f"（命中：{m.group(0)[:40]}）" if m else ""),
            "hit": not m,
        })

    results += check_untested_declaration(text)

    if stripped_blocks:
        results.insert(0, {
            "key": "sanitized_payloads",
            "level": "PASS",
            "check": f"已剥离 {stripped_blocks} 块 base64 内联载荷后再做内容型检查（防误报）",
            "hit": True,
        })
    return results


# ---------------------------------------------------------------------------
# 未实测声明校验（闸门一的产物）
# 规则：正文一旦出现「未实测」，必须同时满足
#   1) 摘要区也声明了  2) 附录 A 也声明了  3) 根因表带「待实测校准」标记
# 三处缺一处即 FAIL —— 防止把「没实测」悄悄藏在附录里混过去
# ---------------------------------------------------------------------------
UNTESTED = "未实测"
CALIBRATION = "待实测校准"


def _region(text: str, start_pat: str, stop_pat: str | None) -> str | None:
    m = re.search(start_pat, text)
    if not m:
        return None
    rest = text[m.start():]
    if stop_pat:
        s = re.search(stop_pat, rest)
        if s:
            return rest[: s.start()]
    return rest[:20000]


def check_untested_declaration(text: str) -> list[dict]:
    out: list[dict] = []
    has_untested = UNTESTED in text
    has_tag = CALIBRATION in text

    if not has_untested:
        out.append({
            "key": "untested_scope",
            "level": "PASS",
            "check": "正文未出现「未实测」字样（已完成实测或未触发闸门一）",
            "hit": True,
        })
        if has_tag:
            out.append({
                "key": "untested_tag_orphan",
                "level": "WARN",
                "check": "出现「待实测校准」标记但正文没有「未实测」声明，二者不一致，请核对",
                "hit": False,
            })
        return out

    n = text.count(UNTESTED)
    summary = _region(text, r"摘要", r"<section")
    appendix = _region(text, r'id="appendix"', None)

    ok_summary = bool(summary and UNTESTED in summary)
    ok_appendix = bool(appendix and UNTESTED in appendix)

    out.append({
        "key": "untested_in_summary",
        "level": "PASS" if ok_summary else "FAIL",
        "check": "「未实测」声明已出现在摘要区（阅者只看摘要就应知道）",
        "hit": ok_summary,
    })
    out.append({
        "key": "untested_in_appendix",
        "level": "PASS" if ok_appendix else "FAIL",
        "check": "「未实测」声明已出现在附录 A 数据口径与局限声明",
        "hit": ok_appendix,
    })
    out.append({
        "key": "untested_calibration_tag",
        "level": "PASS" if has_tag else "FAIL",
        "check": "根因表中依据文档推测的条目已加「待实测校准」标记",
        "hit": has_tag,
    })
    out.append({
        "key": "untested_occurrences",
        "level": "PASS" if n >= 2 else "WARN",
        "check": f"「未实测」出现 {n} 次（建议 >=2：摘要 + 附录各一处）",
        "hit": n >= 2,
    })
    return out


def _page_has_visual(page) -> bool:
    """判断该页是否包含图像或表单类 XObject。
    整页截图页的可提取文字天然极少，不能据此判为空白页。
    （同类假阳性教训：对比度审计若不跳过渐变背景，会把封面整片误报为不合格。）"""
    try:
        res = page.get("/Resources")
        if res is None:
            return False
        xo = res.get("/XObject")
        if xo is None:
            return False
        xo = xo.get_object()
        for key in xo:
            obj = xo[key].get_object()
            if obj.get("/Subtype") in ("/Image", "/Form"):
                return True
    except Exception:
        pass
    return False


def check_pdf(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        out.append({"key": "pdf_dep", "level": "WARN",
                    "check": "未安装 pypdf，跳过 PDF 检查（pip install pypdf）", "hit": False})
        return out

    reader = PdfReader(str(path))
    pages = len(reader.pages)
    blanks = []
    image_only = []
    total = 0
    for i, p in enumerate(reader.pages, 1):
        t = (p.extract_text() or "").strip()
        total += len(t)
        if len(t) < 130:
            if _page_has_visual(p):
                image_only.append(i)   # 图文/整页截图页：正常
            else:
                blanks.append(i)       # 真空白页：异常
    size_mb = path.stat().st_size / 1024 / 1024

    out.append({"key": "pdf_pages", "level": "PASS" if pages >= 10 else "WARN",
                "check": f"PDF 页数（{pages}），体积 {size_mb:.2f} MB", "hit": pages >= 10})
    out.append({"key": "pdf_blank", "level": "PASS" if not blanks else "FAIL",
                "check": "无空白页" + (f"（疑似空白页：{blanks[:8]}）" if blanks else ""),
                "hit": not blanks})
    if image_only:
        out.append({"key": "pdf_image_only", "level": "PASS",
                    "check": f"图文页 {len(image_only)} 页（文字少但含图，已排除在空白页判定外）：{image_only[:10]}",
                    "hit": True})
    out.append({"key": "pdf_density", "level": "PASS" if total / max(pages, 1) >= 250 else "WARN",
                "check": f"平均字符/页（{round(total / max(pages, 1))}，建议 >=250）",
                "hit": total / max(pages, 1) >= 250})
    out += check_page_gaps(path, pages)
    return out


def check_page_gaps(path: Path, pages: int) -> list[dict]:
    """底部留白检查（可选）：逐页渲染，统计内容底界之上的空档占比。

    为什么需要它：pdf_blank 只抓「无内容」的页，而 break-inside:avoid 造成的
    「几乎无内容」的零头孤页（如整页只剩一行表格尾行）字符数可能 >130，逃过
    pdf_blank，却是最刺眼的排版缺陷。此检查把「观感问题」变成可量化指标。
    """
    try:
        import pypdfium2 as pdfium  # type: ignore
    except ImportError:
        return [{"key": "pdf_gap_dep", "level": "PASS",
                 "check": "未安装 pypdfium2，跳过底部留白检查（pip install pypdfium2 可启用）",
                 "hit": True}]

    try:
        doc = pdfium.PdfDocument(str(path))
        gaps = []
        for i in range(len(doc)):
            img = doc[i].render(scale=1.0).to_pil().convert("L")
            W, H = img.size
            px = img.load()
            last = -1
            for y in range(H):
                for x in range(0, W, 2):
                    if px[x, y] < 238:
                        last = y
                        break
            if last >= 0:
                gaps.append((i + 1, (H - 1 - last) / H))
        doc.close()
    except Exception as e:  # 渲染失败不阻塞交付
        return [{"key": "pdf_gap_error", "level": "WARN",
                 "check": f"底部留白检查执行失败，已跳过：{type(e).__name__}", "hit": False}]

    severe = [p for p, g in gaps if g > 0.70]
    moderate = [p for p, g in gaps if 0.45 < g <= 0.70]
    avg = sum(g for _, g in gaps) / max(len(gaps), 1)

    out = [{"key": "pdf_gap_avg", "level": "PASS" if avg <= 0.28 else "WARN",
            "check": f"平均底部留白 {avg:.1%}（建议 <=28%；越高说明越多的块被整体推到下一页）",
            "hit": avg <= 0.28}]
    out.append({"key": "pdf_gap_severe", "level": "PASS" if not severe else "WARN",
                "check": "无「零头孤页」（底部留白 >70%）"
                         + (f"（严重留白页：{severe[:10]}，建议对 .card 解除 break-inside:avoid、"
                            f"给 tr{'{'}break-inside:avoid{'}'} 与 p,li,td{'{'}orphans:3;widows:3{'}'}）"
                            if severe else ""),
                "hit": not severe})
    if moderate:
        out.append({"key": "pdf_gap_moderate", "level": "PASS",
                    "check": f"底部留白 45%–70% 的页（多为章末/表格续页，通常可接受）：{moderate[:10]}",
                    "hit": True})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="业务体验分析报告交付自检")
    ap.add_argument("--src", default="report.src.html", help="源或成品 HTML")
    ap.add_argument("--pdf", default=None, help="导出的 PDF（可选）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"[ERROR] 找不到 {src}", file=sys.stderr)
        return 1

    results = check_html(src.read_text(encoding="utf-8"))
    if args.pdf:
        pdf = Path(args.pdf)
        if pdf.exists():
            results += check_pdf(pdf)
        else:
            results.append({"key": "pdf_missing", "level": "WARN",
                            "check": f"未找到 PDF：{pdf}", "hit": False})

    fails = [r for r in results if r["level"] == "FAIL"]
    warns = [r for r in results if r["level"] == "WARN"]
    passes = [r for r in results if r["level"] == "PASS"]

    if args.json:
        print(json.dumps({
            "source": str(src),
            "summary": {"pass": len(passes), "warn": len(warns), "fail": len(fails)},
            "results": results,
        }, ensure_ascii=False, indent=2))
        return 1 if fails else 0

    print("=" * 68)
    print(f"报告交付自检  |  {src}")
    print("=" * 68)
    for level, items, mark in (("FAIL", fails, "[FAIL]"), ("WARN", warns, "[WARN]")):
        if items:
            print(f"\n-- {level} ({len(items)}) --")
            for r in items:
                print(f"  {mark} {r['check']}")
    print(f"\n-- PASS ({len(passes)}) --")
    for r in passes:
        print(f"  [ OK ] {r['check']}")
    print("\n" + "=" * 68)
    print(f"结果：PASS {len(passes)} / WARN {len(warns)} / FAIL {len(fails)}")
    if fails:
        print("存在 FAIL，请修复后再交付。")
    elif warns:
        print("无阻塞问题，WARN 项建议逐条确认（多为可选增强）。")
    else:
        print("全部通过，可以交付。")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
