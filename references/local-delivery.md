# 本地交付规范（单文件网页 / PDF）

> 用户选「网页」或「PDF」时读这一份。选飞书时读 `online-doc-delivery.md`。
> **推荐顺序永远是：先出单文件 HTML，再由 HTML 转 PDF。** 两者样式同源，不会打架。

## 1. 单文件自包含 HTML

### 1.1 一条硬规范：图片必须内嵌

图片用相对路径引本地 png → 文件一发出去（微信 / 邮件 / 网盘）**手机必断图**。
必须转成 base64 `data:` URI 内联，产物零远程依赖、双击即看。

判据：生成后 `src="data:image` 的数量应等于图片总数，且**不存在任何非 data 的 `src` 外链**。

### 1.2 产出命令

```bash
python scripts/build_handbook.py \
  --md   <攻略>.md \
  --maps <路线图目录>/          # day-DayN.png，按 Day 自动内嵌
  --out  <手册>.html \
  --date 2026-10-01 --days 7    # 可选，用于首屏倒计时
```

脚本自带 Markdown 解析器（标题/表格/列表/任务清单/引用/代码块/图片/分割线），
**零第三方依赖**，换台机器不用先装包。样式与交互直接复用 `assets/travel-handbook.html`
的 `<style>` 与 `<script>`——模板改一次，所有生成的网页同步升级。

> ⚠️ **手册 MD 里不要再写路线图图片行**（`![DayN 路线图](routes/day-DayN.png)`）。
> `build_handbook.py` 与 `md_to_feishu_xml.py` 都会**按 Day 号自动注入** `--maps` 目录里的图，
> MD 里再写一行就是**同一张图渲染两次**。2026-09-30 实测：一本 7 天手册在 HTML 与飞书里
> 各出 **14 张图**（每天两张）。**只留一处机制：图片全部由 `--maps` 注入。**

### 1.3 自动完成的美化映射

| Markdown | 网页呈现 |
|---|---|
| `> 引用`（含 ⚠️/风险/注意） | `.callout warn` 橙色警示条 |
| `> 引用`（含 🛑/禁止/避坑） | `.callout danger` 红色警示条 |
| `> 引用`（含 ✅/实查/推荐） | `.callout ok` 绿色提示条 |
| `> 引用`（其余） | `.callout info` 蓝色提示条 |
| 表格 | 外层包 `.scroll`（窄屏横向滚动，不撑破布局） |
| `- [ ]` 任务项 | `ul.check` 可勾选，localStorage 记忆，关页不丢 |
| `## 二级标题` | 自动生成 `id` 并进顶栏导航（滚动高亮） |
| 路线图 PNG | `.rmap` 卡片，按 Day 序号插进对应小节 |

### 1.4 验收（生成后必查）

- [ ] `src="data:image` 数量 == 图片总数，无非 data 外链
- [ ] 手机窄屏（≤414px）无横向溢出
- [ ] 顶栏导航锚点可跳转
- [ ] 单文件大小建议 ≤ 8MB（超了先压图，否则微信打不开）

## 2. PDF（由 HTML 打印而来）

```bash
python scripts/export_pdf.py --html <手册>.html --out <手册>.pdf --title "带爸妈游某地"
```

### 2.1 为什么打印会翻车（每一条都是真实事故）

| 现象 | 原因 | 脚本里的处置 |
|---|---|---|
| 每日行程整段消失 | `<details>` 折叠块没展开 | 打印前 JS 强制 `d.open=true`，双保险执行两次 |
| 表格/图片被拦腰截断 | 没设分页控制 | `break-inside:avoid` |
| 标题孤零零留在页底 | 标题后内容全被推走 | `h1-h4{break-after:avoid}`、`p{orphans:3;widows:3}` |
| 提示条全变白板，颜色语义丢失 | 没开背景打印 | `print_background=True` |
| 顶栏/进度条/悬浮按钮被印上纸 | 交互控件没隐藏 | `#prog,.topbar,#toTop{display:none}` |
| 没有页码 | 未开页眉页脚 | `display_header_footer=True` + 页脚模板 |

### 2.2 依赖与降级

- 首选 `channel="msedge"` 复用本机 Edge（免下载 Chromium），失败回退 `chromium`；
- 两者都不可用 → 退出码 4；没装 Playwright → 退出码 3，**HTML 本身仍是完好的**，
  让用户用浏览器打开 Ctrl+P 即可，不要因此卡住交付。

## 3. 降级链

```
单文件 HTML（图片内嵌）  ← 首选，任何时候都能出
        ↓ 需要打印/微信直发
      PDF（Playwright）  ← 依赖缺失时降级为「浏览器 Ctrl+P」
        ↓ 用户要在线协作
      飞书（见 online-doc-delivery.md）
```

**没有任何可选依赖也能交付单文件 HTML。** 地图图片缺失时，宁可少图也不能断图——
少图是信息减少，断图是交付事故。
