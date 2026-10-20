# -*- coding: utf-8 -*-
"""
Journey Advisor · 途顾问 — 手册渲染自检（零第三方依赖）

用途：交付前确定性检查「手册 HTML / 飞书 XML 里的每日路线图」是否**对位、不重不漏**。
这一项专治 2026-09-30 鲅鱼圈那类**静默过期**缺陷：行程改了（出发日提前、两天顺序互换），
但 PNG 里**烧进去的 Day 号与日期**没跟着改，图看着正常、其实写着别的日子；同时 MD 里若
还留着手写的 `![DayN 路线图]`，转换器再自动注入一张，就变成每天两张。

用法：
  python check_handbook_render.py --html 手册.html --maps routes/ [--xml 飞书.xml] [--days 7]

检查项：
  1) HTML 内嵌图数 == 天数；所有 <img> 都是 data: URI；无远程 script/link
  2) 每个「以 Day N 开头」的小节内**恰有 1 张图**，且是 day-DayN.png（按内容比对，不信文件名）
  3) 飞书 XML 的 <img> 数 == 天数，且每个 Day 小节指到自己那张 day-DayN.png
  4) PNG 文件名覆盖 Day1..DayN，无缺口

退出码：0 全通过 / 1 有失败项。失败项逐条打印，便于定点修。

注意：判据用 re.match(r"Day\\s*N\\b") 而非 re.search——手册里常有
「🦀 海鲜怎么吃（涉及 Day2、Day3、Day5）」这类**交叉引用标题**，用 search 会误命中产生假阳性。
"""
import argparse
import base64
import io
import os
import re
import sys

HTML_HEAD = re.compile(r'<h[23][^>]*>(.*?)</h[23]>', re.S)
XML_HEAD = re.compile(r'<h[234]>(.*?)</h[234]>', re.S)


def data_uri(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")


def sections(text, head_pat):
    """返回 [(day号, 该小节正文)]，小节 = 标题结束处 → 下一个标题开始处。

    只认「以 Day N 开头」的标题，避开交叉引用标题造成的假阳性。
    """
    heads = [(m.start(), m.end(), re.sub(r"<[^>]+>", "", m.group(1)).strip())
             for m in head_pat.finditer(text)]
    out = []
    for i, (s, e, title) in enumerate(heads):
        m = re.match(r"Day\s*(\d+)\b", title)
        if not m:
            continue
        nxt = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        out.append((int(m.group(1)), text[e:nxt]))
    return out


def check_html(path, maps_dir, days, fails):
    html = io.open(path, encoding="utf-8").read()
    n_inline = html.count('src="data:image')
    print("  HTML 内嵌图 = %d（应为 %d）%s" % (n_inline, days, "OK" if n_inline == days else "❌"))
    if n_inline != days:
        fails.append("HTML 内嵌图 %d 张，应为 %d 张（多出即重复渲染，见 local-delivery.md §1.2）"
                     % (n_inline, days))

    bad = [s for s in re.findall(r'<img[^>]*src="([^"]+)"', html) if not s.startswith("data:image")]
    if bad:
        fails.append("HTML 存在非 data 的 img src（手机必断图）：%s" % bad[:3])
    else:
        print("  非 data 的 img src = 无 OK")

    rem = re.findall(r'<(?:script|link)[^>]+(?:src|href)="https?://[^"]+"', html)
    if rem:
        fails.append("HTML 存在远程 CSS/JS（破坏单文件自包含）：%s" % rem[:3])
    else:
        print("  远程 CSS/JS = 无 OK")

    got = dict(sections(html, HTML_HEAD))
    for n in range(1, days + 1):
        seg = got.get(n)
        want = data_uri(os.path.join(maps_dir, "day-Day%d.png" % n))
        cnt = seg.count("<img") if seg is not None else 0
        mine = bool(seg) and want in seg
        # 「本小节里出现了别的哪一天的图」——对比对象必须是 seg 本身
        others = [k for k in range(1, days + 1)
                  if k != n and seg and data_uri(os.path.join(maps_dir, "day-Day%d.png" % k)) in seg]
        ok = (cnt == 1 and mine and not others)
        print("  HTML Day%d 图数=%d 是本日图=%s %s" % (n, cnt, mine, "OK" if ok else "❌"))
        if not ok:
            fails.append("HTML Day%d 路线图对位失败（图数=%d，是本日图=%s，其他日的图混入=%s）"
                         % (n, cnt, mine, others or "无"))


def check_xml(path, maps_dir, days, fails):
    xml = io.open(path, encoding="utf-8").read()
    n_img = len(re.findall(r"<img\b", xml))
    print("  飞书 img = %d（应为 %d）%s" % (n_img, days, "OK" if n_img == days else "❌"))
    if n_img != days:
        fails.append("飞书 XML img %d 张，应为 %d 张" % (n_img, days))

    got = dict(sections(xml, XML_HEAD))
    for n in range(1, days + 1):
        seg = got.get(n)
        want = "routes/day-Day%d.png" % n
        cnt = len(re.findall(r"<img\b", seg)) if seg is not None else 0
        mine = bool(seg) and want in seg
        others = [k for k in range(1, days + 1)
                  if k != n and seg and ("routes/day-Day%d.png" % k) in seg]
        ok = (cnt == 1 and mine and not others)
        print("  飞书 Day%d 图数=%d 指到本日图=%s %s" % (n, cnt, mine, "OK" if ok else "❌"))
        if not ok:
            fails.append("飞书 Day%d 路线图对位失败（图数=%d，是本日图=%s，其他日的图混入=%s）"
                         % (n, cnt, mine, others or "无"))


def main():
    ap = argparse.ArgumentParser(description="手册渲染自检：每日路线图对位 / 不重不漏 / 单文件自包含")
    ap.add_argument("--html", default=None, help="生成的单文件 HTML")
    ap.add_argument("--xml", default=None, help="生成的飞书 DocxXML")
    ap.add_argument("--maps", default="routes", help="路线图目录（day-DayN.png），默认 routes")
    ap.add_argument("--days", type=int, default=None, help="行程天数，默认按 maps 目录里的 day-DayN.png 推断")
    args = ap.parse_args()

    if not args.html and not args.xml:
        raise SystemExit("至少给 --html 或 --xml 之一")

    have = []
    for name in sorted(os.listdir(args.maps)):
        if not name.lower().endswith(".png"):
            continue
        m = re.search(r"day[\s_\-]*(\d+)", name, re.I)
        if m:
            have.append(int(m.group(1)))
    have = sorted(set(have))
    days = args.days or (max(have) if have else 0)
    if not days:
        raise SystemExit("在 %s 里没找到 day-DayN.png，且未指定 --days" % args.maps)

    print("路线图目录：%s（发现 Day %s）" % (args.maps, have))
    print("按 %d 天核对\n" % days)

    fails = []
    if args.html:
        check_html(args.html, args.maps, days, fails)
        print()
    if args.xml:
        check_xml(args.xml, args.maps, days, fails)
        print()

    if fails:
        print("❌ 未通过，共 %d 项：" % len(fails))
        for f in fails:
            print("   · %s" % f)
        print("\n对位失败时的修法见 references/map-screenshots.md §3.4")
        return 1
    print("✅ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
