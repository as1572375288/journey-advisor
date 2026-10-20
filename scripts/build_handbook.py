#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_handbook.py —— Markdown 攻略 → 单文件自包含 HTML 手册（「网页」交付形态）

为什么要有这个脚本
------------------
攻略的网页形态有一条硬规范：**必须单文件自包含**。
图片若用相对路径引本地 png，文件一发出去（微信/邮件/网盘），手机上必然断图。
所以这里把每张图转成 base64 `data:` URI 内联进 HTML，产物零远程依赖、双击即看。

零第三方依赖
------------
不 import markdown / jinja2 之类：本脚本自带一个够用的 Markdown 解析器
（标题 / 段落 / 表格 / 列表 / 任务清单 / 引用 / 代码块 / 图片 / 分割线 / 行内标记）。
Python 3.8+ 标准库即可跑，换台机器不用先装包。

样式与交互从哪来
----------------
直接复用 `assets/travel-handbook.html` 模板的 `<style>` 与 `<script>`：
主题切换、滚动进度、导航高亮、清单记忆、记账、打印前自动展开折叠块，全部原样继承。
好处是「模板改一次，所有生成的网页同步升级」，不用在脚本里维护第二份 CSS。

USAGE
    python build_handbook.py --md 攻略.md --out 手册.html
    python build_handbook.py --md 攻略.md --maps routes/ --out 手册.html \
        --date 2026-10-01 --days 7

EXIT CODES
    0  成功
    2  输入文件/目录不存在
    3  模板文件缺失（--template 指错或 skill 目录不完整）
"""

import argparse
import base64
import html
import mimetypes
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.join(HERE, "..", "assets", "travel-handbook.html")

# 窄屏修复：模板样式之外的两处补丁，都是实测踩出来的
#   1. .topbar nav 是 flex 子项，默认 min-width:auto 不会收缩，
#      11 个导航链接会把 414px 的手机屏撑破（页面整体横向滚动）。加 min-width:0 才能让它内部滚动。
#   2. 主题按钮不能被压扁。
RESPONSIVE_FIX_CSS = """
.topbar nav{min-width:0;flex:1}
.topbar #themeBtn{flex:none}
.scroll{max-width:100%}
/* 方位示意图/代码块常带超宽 ASCII 画，不加滚动会把手机屏撑破 */
pre{max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}
"""

# 打印样式：让浏览器直接 Ctrl+P 也不至于散架（PDF 脚本会再补强一层）
PRINT_CSS = """
@media print{
  #prog,.topbar,#toTop{display:none!important}
  .hero{padding:20px 16px!important}
  body{font-size:11.5pt}
  section{break-inside:auto}
  details{break-inside:auto}
  details .body{display:block!important}
  .scroll{overflow:visible!important}
  .rmap,table,img{break-inside:avoid;page-break-inside:avoid}
  table{font-size:9.5pt}
  a{color:inherit!important;text-decoration:none}
}
"""


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------
def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def extract_between(text, open_tag, close_tag):
    """抽取模板里第一个 <style>…</style> 或 <script>…</script> 的**内部内容**。"""
    i = text.find(open_tag)
    if i == -1:
        return ""
    i += len(open_tag)
    j = text.find(close_tag, i)
    if j == -1:
        return ""
    return text[i:j]


def b64_data_uri(img_path):
    """本地图片 → base64 data URI。文件不存在返回 None（不静默吞掉，调用方会警告）。"""
    if not os.path.isfile(img_path):
        return None
    mime = mimetypes.guess_type(img_path)[0] or "image/png"
    with open(img_path, "rb") as f:
        raw = f.read()
    return "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode("ascii"))


def slug(i):
    return "sec-%d" % i


def nav_label(text, maxlen=4):
    """顶栏导航短标签：去掉「模块 N：」前缀、去掉括号补充说明、去掉 emoji，再截断。

    导航栏是横排窄条，标签太长会把手机屏撑破或被 CSS 截成半个字（实测过）。
    """
    t = re.sub(r"^[^\u4e00-\u9fa5A-Za-z0-9]+", "", text)          # 去前导 emoji / 标点
    t = re.sub(r"^[^：:]{0,6}[：:]\s*", "", t)                      # 去「模块 0：」这类前缀
    t = re.sub(r"[（(].*?[)）]", "", t)                             # 去括号补充说明
    t = t.replace("+", " ").split()[0] if "+" in t else t
    t = t.strip()
    if not t:
        t = text.strip()
    # 短的原样留着（「天气与穿搭」比「天气与穿」顺眼），长的才截
    return t if len(t) <= maxlen + 1 else t[:maxlen]


# --------------------------------------------------------------------------
# 行内标记：**粗体**  *斜体*  `代码`  [文字](链接)
# --------------------------------------------------------------------------
def inline_render(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank">\1</a>', s)
    return s


# --------------------------------------------------------------------------
# 引用块 → 彩色提示条（对应网页的 .callout）
# --------------------------------------------------------------------------
def classify_callout(text):
    if re.search(r"🛑|⛔|禁止|不要|别|避坑|套路|雷|风险|危险|务必|必须", text):
        return "danger"
    if re.search(r"⚠️|⚠|注意|复查|待确认|可能|警惕|小心|拥挤|紧张", text):
        return "warn"
    if re.search(r"✅|✔|已确认|实查|已订|推荐|建议|贴士|技巧|TIPS", text, re.I):
        return "ok"
    return "info"


# --------------------------------------------------------------------------
# Markdown 解析：返回一个 block 列表
# block = {type: h|p|ul|ol|check|table|quote|code|img|hr}
# --------------------------------------------------------------------------
# 块起始标记：出现即结束当前列表项的「续行」
_BLOCK_START = re.compile(
    r"^(#{1,6}\s|[-*]\s|\d+[.)]\s|>|\||```|!\[|-{3,}$|\*{3,}$|_{3,}$)"
)
# `**标签**：` 开头的行（短标签 ≤20 字）→ 各自成段，
# 避免「预算小计/今日避雷/今日强度/预订提醒」四行被并成一块
_LABEL_LINE = re.compile(r"^\*\*[^*]{1,20}\*\*\s*[：:]")


def _is_continuation(lines, i):
    """列表项续行判定（Markdown lazy continuation）。

    为什么需要：长要点常写成
        - **打车价**：城区→镇上 30 元；返程拼车 10 元/位
          （逻辑是"回程捎一个也算挣"）；去山海广场比去大厦贵
    续行若不被合并，解析器会在第一行处收尾，续行落成独立段落，
    于是在飞书/HTML 里表现为「列表 → 段落 → 新列表」的断档与缩进错乱。

    规则：非空行、且不是任何一个块的起始标记 → 视为上一列表项的续行。
    （真正的段落之间有空行分隔，空行会终止列表，所以不会误并。）
    """
    if i >= len(lines):
        return False
    s = lines[i].strip()
    return bool(s) and not _BLOCK_START.match(s)


def parse_md(text):
    lines = text.split("\n")
    blocks = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 空行
        if not stripped:
            i += 1
            continue

        # 代码块
        if stripped.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # 跳过收尾 ```
            blocks.append({"type": "code", "text": "\n".join(buf)})
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            blocks.append({"type": "h", "level": len(m.group(1)), "text": m.group(2).strip()})
            i += 1
            continue

        # 分割线
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            blocks.append({"type": "hr"})
            i += 1
            continue

        # 表格：当前行以 | 开头，且下一行是分隔行
        if stripped.startswith("|") and i + 1 < n and re.match(r"^\|?[\s:\-\|]+\|[\s:\-\|]*$", lines[i + 1].strip()):
            header = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            blocks.append({"type": "table", "head": header, "rows": rows})
            continue

        # 引用块
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            blocks.append({"type": "quote", "text": "\n".join(buf)})
            continue

        # 任务清单 - [ ] / - [x]
        if re.match(r"^[-*]\s+\[[ xX]\]\s+", stripped):
            items = []
            while i < n and re.match(r"^[-*]\s+\[[ xX]\]\s+", lines[i].strip()):
                s = lines[i].strip()
                done = re.match(r"^[-*]\s+\[[xX]\]", s) is not None
                txt = re.sub(r"^[-*]\s+\[[ xX]\]\s+", "", s)
                i += 1
                while _is_continuation(lines, i):
                    txt += " " + lines[i].strip()
                    i += 1
                items.append((done, txt))
            blocks.append({"type": "check", "items": items})
            continue

        # 无序列表
        if re.match(r"^[-*]\s+", stripped):
            items = []
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()):
                txt = re.sub(r"^[-*]\s+", "", lines[i].strip())
                i += 1
                while _is_continuation(lines, i):
                    txt += " " + lines[i].strip()
                    i += 1
                items.append(txt)
            blocks.append({"type": "ul", "items": items})
            continue

        # 有序列表
        if re.match(r"^\d+[.)]\s+", stripped):
            items = []
            while i < n and re.match(r"^\d+[.)]\s+", lines[i].strip()):
                txt = re.sub(r"^\d+[.)]\s+", "", lines[i].strip())
                i += 1
                while _is_continuation(lines, i):
                    txt += " " + lines[i].strip()
                    i += 1
                items.append(txt)
            blocks.append({"type": "ol", "items": items})
            continue

        # 独立图片行
        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", stripped)
        if m:
            blocks.append({"type": "img", "alt": m.group(1), "src": m.group(2)})
            i += 1
            continue

        # 普通段落（连续非空行合并）
        # 例外：以 `**标签**：` 开头的行各自成段。每日卡的
        # 「预算小计 / 今日避雷 / 今日强度 / 预订提醒」四行本无空行，
        # 若并成一段，后续按语义上色时会被第一条规则整块吃掉（避雷就没了）。
        buf = []
        while i < n and lines[i].strip() and not _BLOCK_START.match(lines[i].strip()):
            if buf and _LABEL_LINE.match(lines[i].strip()):
                break
            buf.append(lines[i].strip())
            i += 1
        if buf:
            blocks.append({"type": "p", "text": "\n".join(buf)})
        else:
            i += 1

    return blocks


# --------------------------------------------------------------------------
# 渲染
# --------------------------------------------------------------------------
def render_blocks(blocks, md_dir, day_maps, drop_first_h1=False):
    out = []
    dropped_h1 = False
    for b in blocks:
        t = b["type"]

        if t == "h":
            # 首个 h1 已经作为首屏大标题渲染，正文里再出现一次就是重复
            if drop_first_h1 and b["level"] == 1 and not dropped_h1:
                dropped_h1 = True
                continue
            out.append('<h%d>%s</h%d>' % (b["level"], inline_render(b["text"]), b["level"]))

        elif t == "p":
            out.append("<p>%s</p>" % inline_render(b["text"]).replace("\n", "<br>"))

        elif t == "hr":
            out.append("<hr>")

        elif t == "quote":
            kind = classify_callout(b["text"])
            out.append('<div class="callout %s">%s</div>'
                       % (kind, inline_render(b["text"]).replace("\n", "<br>")))

        elif t == "code":
            out.append("<pre><code>%s</code></pre>" % html.escape(b["text"]))

        elif t == "ul":
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % inline_render(x) for x in b["items"]))

        elif t == "ol":
            out.append("<ol>%s</ol>" % "".join("<li>%s</li>" % inline_render(x) for x in b["items"]))

        elif t == "check":
            lis = "".join(
                '<li><input type="checkbox"%s><span>%s</span></li>'
                % (" checked" if d else "", inline_render(x))
                for d, x in b["items"]
            )
            out.append('<ul class="check">%s</ul>' % lis)

        elif t == "table":
            th = "".join("<th>%s</th>" % inline_render(c) for c in b["head"])
            trs = "".join(
                "<tr>%s</tr>" % "".join("<td>%s</td>" % inline_render(c) for c in row)
                for row in b["rows"]
            )
            out.append('<div class="scroll"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>'
                       % (th, trs))

        elif t == "img":
            uri = b64_data_uri(os.path.join(md_dir, b["src"])) if not b["src"].startswith(("http", "data:")) else b["src"]
            if uri is None:
                out.append('<p class="foot">[图片缺失：%s]</p>' % html.escape(b["src"]))
            else:
                out.append('<div class="rmap"><img src="%s" style="width:100%%;display:block" alt="%s"></div>'
                           % (uri, html.escape(b["alt"])))

    return "\n".join(out)


def inject_day_maps(rendered_html, day_maps):
    """把每日路线图插到对应 Day 标题所在小节之后。

    做法：按 HTML 里出现的 Day 标题逐个扫描，把图插在该 Day 的下一个同级标题之前。
    匹配不到就全部追加到文末，绝不丢图。
    """
    if not day_maps:
        return rendered_html

    unused = []
    for day, uri in sorted(day_maps.items()):
        pat = re.compile(r"(<h[23][^>]*>[^<]*Day\s*%d\b[^<]*</h[23]>)" % day, re.I)
        m = pat.search(rendered_html)
        card = ('<div class="rmap"><div class="rmap-top"><b>Day %d · 全天路线</b>'
                '<span class="meta">真实路网 · 点到点</span></div>'
                '<img src="%s" style="width:100%%;display:block" alt="Day %d 路线图"></div>'
                % (day, uri, day))
        if m:
            rendered_html = rendered_html[:m.end()] + "\n" + card + rendered_html[m.end():]
        else:
            unused.append(card)

    if unused:
        rendered_html += "\n" + "\n".join(unused)
    return rendered_html


def scan_day_maps(maps_dir):
    """扫描路线图目录：day-Day1.png / Day2.png / day3.png 都能认。"""
    found = {}
    if not maps_dir or not os.path.isdir(maps_dir):
        return found
    for name in sorted(os.listdir(maps_dir)):
        if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue
        m = re.search(r"day[\s_\-]*(\d+)", name, re.I)
        if not m:
            continue
        uri = b64_data_uri(os.path.join(maps_dir, name))
        if uri:
            found[int(m.group(1))] = uri
    return found


def guess_meta(md_text):
    """从正文里抠出天数 / 人数 / 人均预算 / 出发日，给首屏 chips 和记账卡用。"""
    meta = {"days": None, "people": None, "budget": 0, "date": None}

    m = re.search(r"(\d+)\s*天", md_text)
    if m:
        meta["days"] = int(m.group(1))

    m = re.search(r"(\d+)\s*人", md_text)
    if m:
        meta["people"] = int(m.group(1))

    m = re.search(r"人均[^0-9]{0,12}([\d,]{3,})", md_text)
    if m:
        try:
            meta["budget"] = int(m.group(1).replace(",", ""))
        except ValueError:
            pass

    m = re.search(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})", md_text)
    if m:
        meta["date"] = (int(m.group(1)), int(m.group(2)), int(m.group(3)))

    return meta


# --------------------------------------------------------------------------
# 组装
# --------------------------------------------------------------------------
def build(args):
    md_path = os.path.abspath(args.md)
    if not os.path.isfile(md_path):
        print("[build] 找不到 MD：%s" % md_path, file=sys.stderr)
        return 2
    md_dir = os.path.dirname(md_path)

    template = os.path.abspath(args.template or DEFAULT_TEMPLATE)
    if not os.path.isfile(template):
        print("[build] 找不到模板：%s" % template, file=sys.stderr)
        return 3

    tpl = read_text(template)
    style = extract_between(tpl, "<style>", "</style>")
    script = extract_between(tpl, "<script>", "</script>")
    if not style:
        print("[build] 模板里没抽到 <style>，样式会是裸的", file=sys.stderr)

    md_text = read_text(md_path)
    blocks = parse_md(md_text)
    meta = guess_meta(md_text)

    # 标题：--title > MD 首个 h1 > 文件名
    title = args.title
    if not title:
        for b in blocks:
            if b["type"] == "h" and b["level"] == 1:
                title = b["text"]
                break
    if not title:
        title = os.path.splitext(os.path.basename(md_path))[0]

    budget = args.budget if args.budget is not None else meta["budget"]
    date = meta["date"]
    if args.date:
        m = re.match(r"^(20\d{2})-(\d{1,2})-(\d{1,2})$", args.date)
        if m:
            date = (int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # 倒计时起始日写进模板 JS（模板里是 TODO 硬编码）
    if date and script:
        end_d = date
        if args.days:
            # 简易推算：不引入第三方库，按天数直接加（跨月按 30 天近似即可，仅用于倒计时文案）
            import datetime
            try:
                end_d = (datetime.date(*date) + datetime.timedelta(days=int(args.days) - 1)).timetuple()[:3]
            except Exception:
                end_d = date
        script = re.sub(
            r"var start=new Date\([^)]*\), end=new Date\([^)]*\);",
            "var start=new Date(%d,%d,%d), end=new Date(%d,%d,%d);"
            % (date[0], date[1] - 1, date[2], end_d[0], end_d[1] - 1, end_d[2]),
            script,
        )

    body = render_blocks(blocks, md_dir, {}, drop_first_h1=True)
    day_maps = scan_day_maps(args.maps)
    n_maps = len(day_maps)
    body = inject_day_maps(body, day_maps)

    # 导航：取所有 h2
    nav_items = []
    idx = 0
    for b in blocks:
        if b["type"] == "h" and b["level"] == 2:
            idx += 1
            nav_items.append('<a href="#%s">%s</a>'
                             % (slug(idx), html.escape(nav_label(b["text"]))))
    # 给 section 加锚点：把渲染结果里的 h2 逐个替换成带 id 的版本
    def _anchor(mo, box=[0]):
        box[0] += 1
        return '<h2 id="%s">' % slug(box[0])
    body = re.sub(r"<h2>", _anchor, body)

    chips = []
    if meta["days"]:
        chips.append("<span>%d 天</span>" % meta["days"])
    if meta["people"]:
        chips.append("<span>%d 人</span>" % meta["people"])
    if budget:
        chips.append("<span>💰 人均 ¥%s</span>" % format(budget, ","))
    chips.append("<span>单文件 · 离线可看</span>")

    doc = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>{title}</title>
<style>
{style}
{responsive_css}
{print_css}
</style>
</head>
<body>
<div id="prog"></div>
<div class="topbar">
  <nav>{nav}</nav>
  <button class="btn" id="themeBtn">暗色</button>
</div>

<div class="hero">
  <div class="inner">
    <div class="kicker">TRAVEL HANDBOOK · Journey Advisor · 途顾问</div>
    <h1>{title}</h1>
    <div class="chips">{chips}</div>
    <div class="cd" id="countdown">📆 计算中…</div>
  </div>
</div>

<div class="wrap">
{body}
</div>

<section id="budget" data-budget="{budget}" style="max-width:760px;margin:0 auto 30px">
  <h2>路上记一笔（关页不丢）</h2>
  <div class="row">
    <div class="item"><b id="bTotal">—</b><span>总预算(元)</span></div>
    <div class="item"><b id="bSpent">0</b><span>已花</span></div>
    <div class="item"><b id="bLeft">—</b><span>剩余</span></div>
  </div>
  <div class="row">
    <input id="expName" placeholder="项目">
    <input id="expAmt" type="number" placeholder="金额" style="width:110px">
    <button onclick="addExpense()">记一笔</button>
  </div>
  <ul class="exps" id="expList"></ul>
</section>

<p class="foot">本手册由 Journey Advisor · 途顾问 生成 · 图片已内嵌，单文件离线可看<br>
价格为实查 / 参考价，出行前请复查标「待复查」项</p>

<button class="btn" id="toTop">↑ 顶部</button>

<script>
{script}
</script>
</body>
</html>
""".format(
        title=html.escape(title),
        style=style,
        responsive_css=RESPONSIVE_FIX_CSS,
        print_css=PRINT_CSS,
        nav="".join(nav_items),
        chips="".join(chips),
        body=body,
        budget=budget,
        script=script,
    )

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)

    print("HTML  : %s" % out_path)
    print("大小  : %.2f MB" % (os.path.getsize(out_path) / 1024 / 1024))
    print("内嵌图: %d 张" % n_maps)
    print("章节  : %d 个" % len(nav_items))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Markdown 攻略 → 单文件自包含 HTML 手册")
    ap.add_argument("--md", required=True, help="攻略 Markdown 路径")
    ap.add_argument("--out", required=True, help="输出 HTML 路径")
    ap.add_argument("--maps", default=None, help="每日路线图目录（day-DayN.png），会按 Day 内嵌")
    ap.add_argument("--template", default=None, help="手册模板，默认 assets/travel-handbook.html")
    ap.add_argument("--title", default=None, help="手册标题，默认取 MD 首个一级标题")
    ap.add_argument("--date", default=None, help="出发日 YYYY-MM-DD，用于倒计时")
    ap.add_argument("--days", default=None, help="行程天数，配合 --date 算结束日")
    ap.add_argument("--budget", type=int, default=None, help="人均预算总额，覆盖自动识别")
    sys.exit(build(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
