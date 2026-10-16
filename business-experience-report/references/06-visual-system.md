# 06 · 视觉系统与参考图解析

## 一、参考图解析法（用户给图时先做这步）

拿到参考图后**不要直接开始写 HTML**。先解析出设计令牌并复述给用户确认，否则改起来是整篇重做。

五步解析：

1. **主视觉**——找出最大面积的视觉块。记录它的**渐变方向与色标**（起点/中点/终点色值）、圆角半径、内边距量级
2. **配色**——记主色、辅助色、正文色（深）/ 次要色（灰）/ 背景色（浅）/ 状态色（成功·警告·危险）。注意正文灰必须满足 AA 对比度
3. **字号层级**——数出 3–5 档：主标题 / 章节标题 / 卡片标题 / 正文 / 注释。记录字重与字距
4. **组件特征**——药丸标签（chips）的底色与透明度、卡片的阴影强度、指标卡的数字字号、是否有 eyebrow 大写小标题
5. **版面节奏**——最大宽度、卡片间距、是否双栏/三栏网格

把结果写成一张令牌表，问用户：「按这套令牌走，对吗？」

## 二、默认设计令牌（无参考图时用这套）

B 端分析报告基线：**蓝渐变主视觉 + 白底卡片 + 浅蓝背景 + 大数字指标卡**。所有色值已通过 AA 对比度验证。

```css
:root{
  /* 品牌蓝（渐变主视觉） */
  --brand-900:#0A2A6B; --brand-800:#0F3C9E; --brand-700:#1552E0;
  --brand-600:#2563EB; --brand-500:#3B82F6; --brand-300:#93C5FD; --brand-100:#DBEAFE;
  /* 青色强调 */
  --cyan-500:#06B6D4; --cyan-400:#22D3EE; --cyan-200:#A5F3FC;
  /* 背景与卡片 */
  --bg:#F3F6FC; --card:#FFFFFF;
  /* 文字（muted 已调深以满足 AA 4.5:1） */
  --ink:#0B1220; --ink2:#334155; --muted:#5A6A80; --muted2:#5B6B84;
  --line:#E3E9F2; --line2:#EEF3FA;
  /* 状态色 */
  --ok:#0EA371; --warn:#D97706; --danger:#DC2626;
  /* 圆角 / 阴影 / 宽度 */
  --radius:18px; --radius-lg:28px; --radius-sm:12px;
  --shadow:0 12px 34px rgba(15,42,107,.09);
  --shadow-sm:0 4px 14px rgba(15,42,107,.06);
  --maxw:1180px;
}
```

**封面渐变（已验证白字可达 AA）：**
```css
background:
  radial-gradient(120% 140% at 88% 6%, rgba(165,243,252,.40) 0%, rgba(165,243,252,0) 46%),
  linear-gradient(128deg,#08215C 0%,#0F3AAB 32%,#1450CC 62%,#1B6BDF 100%);
```

**阶段卡三档渐变（保证白字 ≥4.5:1，且由深到亮有递进）：**
```css
.phase:nth-child(1) .phase-hd{background:linear-gradient(135deg,#0B2E7A,#1246C8)}
.phase:nth-child(2) .phase-hd{background:linear-gradient(135deg,#103C9E,#1450D2)}
.phase:nth-child(3) .phase-hd{background:linear-gradient(135deg,#1552E0,#1668DE)}
```
> 反例：`#4FC3F7` 这类浅青做渐变末端时，白字对比度会跌破 3:1，不要用在需要白字的卡片上。

## 三、骨架用法

`assets/report-skeleton.html` 已内置下面全部组件与验证过的 CSS，**整份复制后填充**，不要从零写样式。

- 占位符约定：双花括号大写名，如 `{{PRODUCT_NAME}}`、`{{R1}}`、`{{P1_GOAL}}`
- 列出全部待填项：`grep -o '{{[A-Z0-9_]*}}' report.html | sort -u`
- 交付前确认没有残留占位符（`check_report.py` 会检查）
- 非求职场景：整段删除附录 B
- 不需要的组件段直接删，不要留着空壳

## 四、组件清单（骨架里已内置）

| 组件 | class | 用途 |
|---|---|---|
| 封面 | `.hero` | 品牌标 + eyebrow + 主标题 + 副标题 + chips + meta |
| 关键数字卡 | `.kpi-grid` / `.kpi` | 4 张，含数字 / 说明 / 来源 |
| 阅读导航 | `.nav` | 三章入口卡（打印时自动隐藏） |
| 章节标题 | `.sec` / `.sec-no` | 左侧渐变编号方块 + 标题 + 副标题 |
| 子节标题 | `.subsec` | 左侧 4px 竖线 |
| 卡片 | `.card` | 通用内容容器 |
| 表格 | `.tbl-wrap` + `table` | 圆角包裹，表头浅蓝 |
| 标签 | `.tag` `.t-p0` `.t-p1` `.t-p2` `.t-ok` | 优先级 / 状态 |
| 亮点·不足双栏 | `.pm` / `.pm-col` | 顶部色条区分 |
| 提示条 | `.note` / `.note.warn` / `.note.dim` | 强调与口径声明 |
| 图示块 | `.diagram` + `.figcap` | SVG 容器 + 图注 |
| 证据组 | `.evi` / `.evi-no` / `.evi-read` | 论点—证据图分组 |
| 阶段卡 | `.phases` / `.phase` | 三阶段路线图 |
| 指标树 | `.tree` | 左标签右内容的分层行 |
| 附录来源 | `.srcs` | 带 URL 的来源列表 |

## 五、图示绘制规则（SVG）

经验教训，都是踩过的坑：

1. **SVG 内的注释文字不要超出 viewBox**——超出会被直接裁掉且不报错。图下注释用 HTML 的 `.figcap` 或 `.note.dim` 承载，不要塞进 SVG
2. **标注框不要压住图形**——把「最大断崖」之类标注移到图形外侧（左侧或上方），用引导线连接
3. **文字颜色必须在 SVG 内联显式设置**，不要依赖外部 CSS 类，否则可能继承成黑色或不可见
4. **长标签要缩短**——卡片内的标签一旦超宽会撑破布局
5. **宽度适配**：`viewBox="0 0 W H"` + `max-width:100%; height:auto`，W 建议 ≤ 1000

## 六、打印与响应式规则

```css
@page{size:A4; margin:12mm}
@media print{
  body{background:#fff; font-size:12.4px}
  .wrap{max-width:none; padding:0}
  .card,.kpi,.shot,.phase,.tree,.diagram,.pm-col,.nav a{box-shadow:none!important}
  .card,.kpi,.phase,.shot,.pm-col,.tree,.diagram{break-inside:avoid; page-break-inside:avoid}
  .sec,.subsec{break-after:avoid; page-break-after:avoid}
  .hero{break-inside:avoid; margin-top:0}
  .nav{display:none}
  a{color:inherit; text-decoration:none}
}
@media (max-width:900px){
  /* 所有多栏网格降为单栏 */
  .kpi-grid,.grid3,.grid4,.phases,.grid2,.pm,.shots,.nav{grid-template-columns:1fr}
  .tree-row{grid-template-columns:1fr}
}
```

要点：`@page margin` 收紧到 12mm 可避免底部大片留白；卡片 `break-inside:avoid` 防止跨页断裂；`@media print` 里隐藏 `.nav`（导航在纸上没意义）。

## 七、视觉自检

| 检查项 | 标准 | 工具 |
|---|---|---|
| 正文对比度 | ≥ 4.5:1（大字 ≥ 3:1） | `scripts/audit_visual.js` |
| 横向溢出 | 无（`scrollWidth <= innerWidth`） | 同上 |
| 图片加载 | 0 张 broken | 同上 |
| PDF 页数分布 | 无空白页（每页文本 ≥ 130 字符） | `scripts/check_report.py` |
| 图示截断 | 目视复核每个 `.diagram` | 渲染截图 |

**注意**：对比度脚本必须**跳过带 `background-image` 的元素**（渐变背景取不到单一底色，会把整片封面误报为不合格）。若不做这个排除，你会收到几十条假告警。
