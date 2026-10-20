#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_pdf.py —— 单文件 HTML 手册 → 打印友好 PDF（「PDF」交付形态）

为什么单独一个脚本
------------------
网页好看 ≠ 打印好看。浏览器打印时会把屏幕样式直接搬到纸上，典型翻车现场：
  · 折叠块 `<details>` 没展开 → 每日行程整段被吞掉
  · 表格/图片被拦腰截断，一半在这页一半在下页
  · 标题孤零零留在页底，正文全跑到下一页
  · 背景色不打印 → 提示条全变白板，颜色语义（警示/推荐）丢失
  · 顶栏、进度条、悬浮按钮被一起印上去
所以这里在打印前注入一整套 `@media print`，把上面每一条都堵住。

依赖
----
Playwright（可选依赖）。优先复用本机 Edge（`channel="msedge"`），省掉下载 Chromium；
本机没有 Edge 时回退 `chromium`。两者都没有 → 退出码 4，并给出降级建议。
没有 Playwright → 退出码 3，HTML 仍是完好的，可以直接用浏览器 Ctrl+P。

USAGE
    python export_pdf.py --html 手册.html --out 手册.pdf
    python export_pdf.py --html 手册.html --out 手册.pdf --title "带爸妈游某地" --format A4

EXIT CODES
    0  成功
    2  输入 HTML 不存在
    3  未安装 Playwright（可降级：让用户用浏览器打印）
    4  Edge 与 Chromium 都不可用
"""

import argparse
import os
import sys

# 打印样式：每一条都对应一个真实翻车场景，改之前先想清楚要付什么代价
PRINT_CSS = """
@page{ size:{format}; margin:{margin}; }
html,body{ background:#fff!important; }
body{ font-size:10.5pt; line-height:1.62; }

/* 交互控件不上纸 */
#prog,.topbar,#toTop,.btn{ display:none!important; }
.hero{ padding:16px 14px!important; }
.hero h1{ font-size:19pt!important; }

/* 折叠块必须展开，否则每日行程被吞 */
details{ break-inside:auto; }
details .body{ display:block!important; }
details[open] .body, details .body{ display:block!important; }

/* 不许被拦腰截断 */
.rmap, table, img, .callout, pre{ break-inside:avoid; page-break-inside:avoid; }
.scroll{ overflow:visible!important; }
table{ font-size:9pt; width:100%!important; }
img{ max-width:100%!important; max-height:230mm; }

/* 标题不落单：标题后至少跟 3 行内容 */
h1,h2,h3,h4{ break-after:avoid; page-break-after:avoid; }
h2{ margin-top:14pt!important; }
p{ orphans:3; widows:3; }

/* 每个 Day / 一级小节尽量新起一页，读起来才像手册 */
section{ break-inside:auto; }

/* 链接不再显示成蓝下划线 */
a{ color:inherit!important; text-decoration:none!important; }
"""

FOOTER = """
<div style="width:100%;font-size:8px;color:#888;padding:0 12mm;
     display:flex;justify-content:space-between;">
  <span>{title}</span>
  <span>第 <span class="pageNumber"></span> / <span class="totalPages"></span> 页</span>
</div>
"""


def build_pdf(args):
    html_path = os.path.abspath(args.html)
    if not os.path.isfile(html_path):
        print("[pdf] 找不到 HTML：%s" % html_path, file=sys.stderr)
        return 2

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[pdf] 未安装 Playwright，无法自动出 PDF。", file=sys.stderr)
        print("      安装：pip install playwright（或用浏览器打开 HTML 直接 Ctrl+P）", file=sys.stderr)
        return 3

    import pathlib

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    # 注意：CSS 里满是 {width:100%} 这类花括号，用 str.format() 会把它们当占位符
    # 直接 KeyError 崩掉（实测踩过）。这里老老实实用 replace。
    css = PRINT_CSS.replace("{format}", args.format.lower()).replace("{margin}", args.margin)

    with sync_playwright() as pw:
        browser = None
        last_err = None
        for launcher in ("msedge", "chromium"):
            try:
                if launcher == "msedge":
                    browser = pw.chromium.launch(channel="msedge")
                else:
                    browser = pw.chromium.launch()
                break
            except Exception as e:                      # noqa: BLE001 - 只是想换下一个引擎
                last_err = e
                browser = None
        if browser is None:
            print("[pdf] Edge 与 Chromium 都不可用：%s" % last_err, file=sys.stderr)
            return 4

        page = browser.new_page(viewport={"width": 1024, "height": 1400})
        page.goto(pathlib.Path(html_path).as_uri())
        page.wait_for_timeout(1200)

        # 打印前强制展开所有折叠块（双保险：JS 的 beforeprint 可能不触发）
        page.evaluate("document.querySelectorAll('details').forEach(d=>d.open=true)")
        page.add_style_tag(content=css)
        page.evaluate("document.querySelectorAll('details').forEach(d=>d.open=true)")
        page.wait_for_timeout(800)

        page.pdf(
            path=out_path,
            format=args.format,
            print_background=True,          # 关键：提示条/表头的背景色靠它保住
            margin={
                "top": args.margin, "bottom": args.margin,
                "left": args.margin, "right": args.margin,
            },
            display_header_footer=args.footer,
            footer_template=FOOTER.format(title=args.title or "") if args.footer else "",
            header_template="<div></div>" if args.footer else "",
        )
        browser.close()

    print("PDF   : %s" % out_path)
    print("大小  : %.2f MB" % (os.path.getsize(out_path) / 1024 / 1024))
    return 0


def main():
    ap = argparse.ArgumentParser(description="单文件 HTML 手册 → 打印友好 PDF")
    ap.add_argument("--html", required=True, help="输入 HTML（build_handbook.py 的产物）")
    ap.add_argument("--out", required=True, help="输出 PDF 路径")
    ap.add_argument("--format", default="A4", help="纸张，默认 A4")
    ap.add_argument("--margin", default="10mm", help="页边距，默认 10mm")
    ap.add_argument("--title", default=None, help="页脚标题")
    ap.add_argument("--no-footer", dest="footer", action="store_false", help="不加页码页脚")
    ap.set_defaults(footer=True)
    sys.exit(build_pdf(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
