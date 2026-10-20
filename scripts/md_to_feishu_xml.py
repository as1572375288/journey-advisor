#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md_to_feishu_xml.py —— Markdown 攻略 → 飞书 DocxXML（飞书排版美化形态）

为什么需要它
------------
直接 `drive +import` 一个 .md，飞书只会得到：灰色竖线引用块 + 平铺表格 + 机械编号标题。
实测一份公认「排版好看」的飞书攻略，它的做法是：

  · 23 个 **callout 高亮块**承载要点（💡 🎯 🧥 …），而不是把要点散在正文段落里
  · 3 组 **grid 分栏**做并排信息
  · **只用一个 h2 层级**（13 个），不做 h3/h4 深嵌套
  · **标题自带结论**：「每天怎么玩：Day 3 环线日——大潮赶海 + 北海团山」
    而不是「模块 4：每日行程」这种机械编号
  · 表格简洁（4 列以内），表头浅灰底

本脚本把 Markdown 按这套规律翻译成 DocxXML，再用 lark-cli 写进飞书：

    python md_to_feishu_xml.py --md 攻略.md --out 飞书.xml [--maps routes/]
    cd <地图目录所在层>
    lark-cli docs +create --as user --doc-format xml --content @飞书.xml

EXIT CODES
    0  成功
    2  输入 MD 不存在
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from build_handbook import parse_md, inline_render
except ImportError:                       # 单独拷走这个脚本时用内置兜底
    parse_md = inline_render = None


# 高亮块配色：背景用 light-*（克制），强提醒才上 medium-*
CALLOUT_RULES = [
    (r"🛑|⛔|避坑|套路|不要|别|禁止|务必|危险|骗局|宰客", "🛑", "light-red",    "red"),
    (r"⚠️|⚠|注意|复查|待确认|可能|警惕|小心|紧张|拥挤|限流", "⚠️", "light-orange", "orange"),
    (r"💰|¥|预算|花费|价格",                              "💰", "light-green",  "green"),
    (r"♨️|温泉",                                        "♨️", "light-blue",   "blue"),
    (r"🦀|赶海|潮汐|退潮",                                "🦀", "light-blue",   "blue"),
    (r"🍽|🦐|吃|餐|早市|市场|人均",                        "🍽", "light-green",  "green"),
    (r"🚗|🚌|打车|高铁|车次|交通|停车",                     "🚗", "light-purple", "purple"),
    (r"🧥|穿|带|装备|证件|药品",                           "🧥", "light-yellow", None),
    (r"🎯|关键|结论|核心|重点|记住",                        "🎯", "medium-blue",  None),
    (r"✅|✔|已订|已确认|已核查",                          "✅", "light-green",  "green"),
]


# 段落级高亮：段落以 `**标签**：` 开头、且标签命中语义 → 整段升为高亮卡片
# 这是「网页版视觉」的核心——每个要点是一张带色的卡，而不是一段灰色正文
PARA_CALLOUT_RULES = [
    (r"避雷|最大风险|风险",             "🛑", "light-red",    "red"),
    (r"重要调整|调整|注意|警惕|待复查",   "⚠️", "light-orange", "orange"),
    (r"交通提示|今日交通",               "🚗", "light-purple", "purple"),
    (r"一句话|怎么玩|核心|结论",         "🎯", "light-blue",   "blue"),
    (r"给谁做|这份攻略给谁",             "👥", "light-blue",   "blue"),
    (r"行程骨架|骨架|方位",              "🧭", "light-blue",   "blue"),
    (r"预算小计|今日预算|总账|人均",      "💰", "light-green",  "green"),
    (r"老人提示",                        "👵", "light-yellow", None),
]


# 行首 emoji → 配色（优先级最高：作者写了什么 emoji，就用什么色）
EMOJI_TONE = {
    "🛑": ("light-red", "red"),      "⛔": ("light-red", "red"),
    "⚠": ("light-orange", "orange"),
    "📌": ("light-blue", "blue"),    "💡": ("light-blue", None),
    "✅": ("light-green", "green"),  "✔": ("light-green", "green"),
    "💰": ("light-green", "green"),  "🥠": ("light-green", "green"),
    "🍽": ("light-green", "green"),  "🦐": ("light-green", "green"),
    "🦀": ("light-blue", "blue"),    "🌊": ("light-blue", "blue"),
    "♨": ("light-blue", "blue"),     "🧭": ("light-blue", "blue"),
    "👥": ("light-blue", "blue"),
    "🚗": ("light-purple", "purple"), "🚌": ("light-purple", "purple"),
    "🚉": ("light-purple", "purple"), "🎫": ("light-purple", "purple"),
    "🔄": ("light-purple", "purple"),
    "🧥": ("light-yellow", None),    "👵": ("light-yellow", None),
    "🧓": ("light-yellow", None),
    "🎯": ("medium-blue", None),     "🗑": ("light-gray", None),
}


def tone_by_leading_emoji(text):
    """文本（或标签）以某个 emoji 开头 → 直接给出配色。"""
    t = text.lstrip("*# ").strip()
    if not t:
        return None
    # 先试两字符（含变体选择符），再试单字符
    for n in (2, 1):
        head = t[:n]
        key = head.rstrip("\ufe0f")
        if key in EMOJI_TONE:
            return key, EMOJI_TONE[key][0], EMOJI_TONE[key][1]
    return None


def pick_callout(text):
    lead = tone_by_leading_emoji(text)
    if lead:
        return lead
    for pat, emoji, bg, fg in CALLOUT_RULES:
        if re.search(pat, text):
            return emoji, bg, fg
    return "💡", "light-blue", None


def pick_para_callout(text):
    """段落若以 `**标签**：` 开头：先按标签语义上色，其次按标签自带 emoji；否则 None。

    标签后无正文的（`**⚠️ 今日避雷**：` 独占一行、正文在下一段）一律不升级，
    否则飞书里会出现一张空的高亮卡片。
    """
    m = re.match(r"^\*\*([^*]{1,16})\*\*\s*[：:]", text)
    if not m:
        return None
    if not text[m.end():].strip():
        return None
    label = m.group(1)
    for pat, emoji, bg, fg in PARA_CALLOUT_RULES:
        if re.search(pat, label):
            return emoji, bg, fg
    return tone_by_leading_emoji(label)


def clean_heading(text):
    """标题去机械编号，保留「自然语言：结论」——参考文档的做法。"""
    t = re.sub(r"^模块\s*\d+\s*[：:]\s*", "", text)
    t = re.sub(r"^第\s*\d+\s*章\s*[：:]\s*", "", t)
    return t.strip() or text.strip()


def to_xml(blocks, maps_dir=None, flatten=False, map_prefix="", para_callout=True):
    """把解析好的 block 列表翻译成 DocxXML 片段。"""
    out = []
    first_h2_seen = False
    pending_hero = []          # 首屏的两个要点 → 两栏 grid
    in_hero = False

    for b in blocks:
        t = b["type"]

        if t == "h":
            lvl = b["level"]
            text = b["text"]
            if lvl == 1:
                continue                                  # 标题由 <title> 承担
            if lvl == 2:
                if not first_h2_seen:
                    first_h2_seen = True
                    in_hero = True
                out.append("<h2>%s</h2>" % inline_render(clean_heading(text)))
            else:
                # 扁平化：h3 及以下统一降为 h2，避免深嵌套（参考文档只用一个层级）
                if flatten:
                    out.append("<h2>%s</h2>" % inline_render(clean_heading(text)))
                else:
                    out.append("<h%d>%s</h%d>" % (lvl, inline_render(text), lvl))
            continue

        if t == "quote":
            emoji, bg, fg = pick_callout(b["text"])
            body = inline_render(b["text"]).replace("\n", "<br/>")
            attr = ' emoji="%s" background-color="%s"' % (emoji, bg)
            if fg:
                attr += ' text-color="%s"' % fg
            card = "<callout%s><p>%s</p></callout>" % (attr, body)
            # 首屏的前两个要点并排成两栏
            if in_hero and len(pending_hero) < 2:
                pending_hero.append(card)
                if len(pending_hero) == 2:
                    out.append('<grid><column width-ratio="0.5">%s</column>'
                               '<column width-ratio="0.5">%s</column></grid>'
                               % (pending_hero[0], pending_hero[1]))
                    in_hero = False
            else:
                out.append(card)
            continue

        if t == "p":
            text = b["text"]
            body = inline_render(text).replace("\n", "<br/>")
            picked = pick_para_callout(text) if para_callout else None
            if picked:
                emoji, bg, fg = picked
                attr = ' emoji="%s" background-color="%s"' % (emoji, bg)
                if fg:
                    attr += ' text-color="%s"' % fg
                out.append("<callout%s><p>%s</p></callout>" % (attr, body))
            else:
                out.append("<p>%s</p>" % body)
            continue

        if t == "hr":
            out.append("<hr/>")
            continue

        if t == "ul":
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % inline_render(x) for x in b["items"]))
            continue

        if t == "ol":
            out.append("<ol>%s</ol>" % "".join("<li>%s</li>" % inline_render(x) for x in b["items"]))
            continue

        if t == "check":
            out.append("".join('<checkbox done="%s">%s</checkbox>'
                               % ("true" if d else "false", inline_render(x))
                               for d, x in b["items"]))
            continue

        if t == "table":
            th = "".join('<th background-color="light-blue"><p>%s</p></th>' % inline_render(c)
                         for c in b["head"])
            trs = "".join("<tr>%s</tr>" % "".join("<td><p>%s</p></td>" % inline_render(c) for c in row)
                          for row in b["rows"])
            out.append("<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (th, trs))
            continue

        if t == "code":
            out.append("<pre><code>%s</code></pre>" % b["text"].replace("&", "&amp;").replace("<", "&lt;"))
            continue

        if t == "img":
            src = b["src"]
            if src.startswith("http") or src.startswith("data:"):
                out.append('<img href="%s"/>' % src)
            else:
                out.append('<img path="@./%s"/>' % src)
                # 路线图后补一行来源说明（网页版 rmap 的 foot 行）
                if "route" in src.lower():
                    out.append('<p>🗺️ 按高德实查里程与方位绘制 · 非路网截图 · 里程车程为出发前实测值</p>')
            continue

    # 每日路线图：按 Day 序号插到对应标题后面
    if maps_dir and os.path.isdir(maps_dir):
        pics = {}
        for name in sorted(os.listdir(maps_dir)):
            m = re.search(r"day[\s_\-]*(\d+)", name, re.I)
            if m and name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                # 写入路径用「lark-cli 执行目录」的相对前缀，扫描用真实目录
                pics[int(m.group(1))] = "%s/%s" % (map_prefix.rstrip("/"), name) if map_prefix else name
        xml = "\n".join(out)
        for day in sorted(pics):
            pat = re.compile(r"(<h[234]>[^<]*Day\s*%d\b[^<]*</h[234]>)" % day, re.I)
            xml = pat.sub(lambda mo: mo.group(1) + '\n<img path="@./%s"/>' % pics[day], xml, count=1)
        out = [xml]

    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Markdown → 飞书 DocxXML（高亮块 + 分栏 + 扁平标题）")
    ap.add_argument("--md", required=True, help="攻略 Markdown")
    ap.add_argument("--out", required=True, help="输出 XML")
    ap.add_argument("--maps", default=None, help="路线图目录（本机真实路径，用于扫描）")
    ap.add_argument("--map-prefix", default="routes", help="图在 XML 里写成的相对路径前缀，需与 lark-cli 执行目录匹配（默认 routes）")
    ap.add_argument("--title", default=None, help="文档标题，默认取 MD 首个 h1")
    ap.add_argument("--flatten", action="store_true", help="把 h3 及以下也压成 h2（默认保留原层级）")
    ap.add_argument("--no-para-callout", action="store_true",
                    help="关闭「语义段落 → 高亮卡片」升级（默认开启）")
    args = ap.parse_args()

    if parse_md is None:
        print("[xml] 找不到 build_handbook.py（应与之放在同一 scripts/ 目录）", file=sys.stderr)
        return 2
    if not os.path.isfile(args.md):
        print("[xml] 找不到 MD：%s" % args.md, file=sys.stderr)
        return 2

    text = open(args.md, "r", encoding="utf-8").read()
    blocks = parse_md(text)

    title = args.title
    if not title:
        for b in blocks:
            if b["type"] == "h" and b["level"] == 1:
                title = b["text"]
                break
    if not title:
        title = os.path.splitext(os.path.basename(args.md))[0]

    body = to_xml(blocks, args.maps, flatten=args.flatten, map_prefix=args.map_prefix,
                  para_callout=not args.no_para_callout)
    doc = "<title>%s</title>\n%s" % (title.replace("&", "&amp;").replace("<", "&lt;"), body)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(doc)

    print("XML   : %s" % os.path.abspath(args.out))
    print("标题  : %s" % title)
    print("高亮块: %d 个" % doc.count("<callout"))
    print("分栏  : %d 组" % doc.count("<grid>"))
    print("表格  : %d 张" % doc.count("<table>"))
    print("图片  : %d 张" % len(re.findall(r"<img ", doc)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
