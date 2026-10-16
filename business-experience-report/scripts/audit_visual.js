/* audit_visual.js -- 报告视觉自动审计（在浏览器里执行，输出 JSON）
 *
 * 用法（配合 agent-browser）：
 *   1) 打开报告：
 *      agent-browser open "file:///绝对路径/报告.html"
 *   2) 注入本文件内容执行（注意：agent-browser eval 没有 --file 选项，
 *      直接传字符串会因引号/换行被 shell 破坏而报
 *      "SyntaxError: Unexpected token"，必须走 --stdin）：
 *      agent-browser eval --stdin < scripts/audit_visual.js
 *      或 cat scripts/audit_visual.js | agent-browser eval --stdin
 *
 * 检查项：
 *   - 文字对比度（WCAG AA：正文 >= 4.5:1，大字 >= 3:1）
 *   - 横向溢出（scrollWidth > innerWidth）
 *   - 图片是否 broken
 *   - 结构计数（证据组 / 表格 / 图表 / 关键组件）
 *
 * 重要：对比度计算会【跳过带 background-image 的元素】（渐变背景取不到单一
 * 底色，否则封面整片会被误报为不合格）。这些元素计入 gradientSkipped。
 */
(function () {
  function srgb(v) {
    v /= 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  }
  function lum(c) {
    return 0.2126 * srgb(c[0]) + 0.7152 * srgb(c[1]) + 0.0722 * srgb(c[2]);
  }
  function parseRGB(s) {
    var m = String(s).match(/[\d.]+/g);
    return m ? m.slice(0, 3).map(Number) : null;
  }
  function alphaOf(s) {
    var m = String(s).match(/rgba?\(([^)]+)\)/);
    if (!m) return 1;
    var parts = m[1].split(",");
    return parts.length >= 4 ? parseFloat(parts[3]) : 1;
  }
  /* 向上找最近的「有效纯色背景」。命中渐变（background-image）时返回 null = 跳过 */
  function bgOf(el) {
    var e = el;
    while (e && e !== document.documentElement) {
      var s = getComputedStyle(e);
      if (s.backgroundImage && s.backgroundImage !== "none") return null;
      if (alphaOf(s.backgroundColor) > 0.85) {
        var c = parseRGB(s.backgroundColor);
        if (c) return c;
      }
      e = e.parentElement;
    }
    return [243, 246, 252]; /* 页面默认底 */
  }

  var fails = [];
  var checked = 0;
  var gradientSkipped = 0;

  document.querySelectorAll("body *").forEach(function (el) {
    if (el.children.length > 0 && !el.matches(".pill,.kpi-num")) return;
    var text = (el.textContent || "").trim();
    if (text.length < 2) return;
    if (el.offsetParent === null && getComputedStyle(el).position !== "fixed") return;

    var cs = getComputedStyle(el);
    var fg = parseRGB(cs.color);
    if (!fg) return;

    var bg = bgOf(el);
    if (!bg) {
      gradientSkipped++;
      return;
    }
    checked++;

    var L1 = lum(fg);
    var L2 = lum(bg);
    var ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    var size = parseFloat(cs.fontSize);
    var bold = parseInt(cs.fontWeight, 10) >= 700;
    var need = size >= 24 || (size >= 18.66 && bold) ? 3 : 4.5;

    if (ratio < need) {
      fails.push({
        text: text.slice(0, 34),
        color: cs.color,
        fontSize: size,
        ratio: Math.round(ratio * 100) / 100,
        need: need
      });
    }
  });

  var imgs = Array.prototype.slice.call(document.images);
  var broken = imgs.filter(function (i) {
    return !i.complete || i.naturalWidth === 0;
  });

  /* 校验 SVG 内文字是否越出 viewBox（静默裁切防护） */
  var svgClips = [];
  document.querySelectorAll("svg").forEach(function (svg, idx) {
    var vb = svg.getAttribute("viewBox");
    if (!vb) return;
    var p = vb.split(/\s+/).map(Number);
    if (p.length !== 4) return;
    var vbW = p[2];
    svg.querySelectorAll("text").forEach(function (t) {
      try {
        var bb = t.getBBox();
        if (bb.x + bb.width > vbW + 2 || bb.x < -2) {
          svgClips.push({
            svg: idx,
            text: (t.textContent || "").trim().slice(0, 28),
            right: Math.round(bb.x + bb.width),
            viewBoxWidth: vbW
          });
        }
      } catch (e) {}
    });
  });

  return JSON.stringify({
    contrast: { checked: checked, gradientSkipped: gradientSkipped, fails: fails.length, sample: fails.slice(0, 12) },
    overflowX: document.documentElement.scrollWidth > window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    images: { total: imgs.length, broken: broken.length },
    svgTextOutOfViewBox: svgClips,
    structure: {
      evidenceGroups: document.querySelectorAll(".evi").length,
      diagrams: document.querySelectorAll(".diagram").length,
      tables: document.querySelectorAll("table").length,
      phases: document.querySelectorAll(".phase").length,
      kpis: document.querySelectorAll(".kpi").length,
      sections: document.querySelectorAll("section").length
    },
    htmlChars: document.documentElement.outerHTML.length
  }, null, 2);
})();
