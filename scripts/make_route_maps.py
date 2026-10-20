# -*- coding: utf-8 -*-
"""把高德/百度/腾讯真实地图"点到点"路线截图拼成每日全天路线图，顶部加路程横幅。

用法：
  python make_route_maps.py --config route_config.json

配置 JSON：
{
  "out_dir": "routes/final",
  "font": null,                       # null = 自动探测系统中文字体
  "days": [
    {"file": "final-Day1.png",
     "title": "Day1 · 10/1 到达日",
     "sub": "车站 → 酒店｜驾车约32分钟 · 20.5公里",
     "images": [{"path": "routes/map-Day1.png", "width": 760, "label": "车站→酒店"}]},
    {"file": "final-Day3.png",
     "title": "Day3 · 环线日",
     "sub": "住处→A 约42分·29.6km；A→B 约38分·27.3km",
     "images": [{"path": "routes/map-Day3a.png", "width": 720, "label": "① 住处→A"},
                {"path": "routes/map-Day3b.png", "width": 720, "label": "② A→B"}]}
  ]
}

单段直接出图，多段纵向拼接；时长/公里必须照抄地图面板读数。
"""
import argparse
import json
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("需要 Pillow：pip install pillow")

BANNER_H = 104
LABEL_H = 34
BG = (31, 78, 121)
LABEL_BG = (240, 244, 249)
LABEL_FG = (60, 72, 88)
FG = (255, 255, 255)
SUB = (205, 225, 245)

FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


def pick_font(explicit=None):
    """跨平台选一个能渲染中文的字体，找不到就退回 Pillow 默认。"""
    for p in ([explicit] if explicit else []) + FONT_CANDIDATES:
        if p and os.path.exists(p):
            return p
    return None


def font_at(path, size):
    try:
        return ImageFont.truetype(path, size) if path else ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def fit_text(draw, text, font_path, max_w, start_size, min_size=14):
    """按可用宽度自动缩字号，保证不溢出横幅。"""
    size = start_size
    while size >= min_size:
        f = font_at(font_path, size)
        if draw.textlength(text, font=f) <= max_w:
            return f, size
        size -= 1
    return font_at(font_path, min_size), min_size


def load(path, width):
    if not os.path.exists(path):
        raise FileNotFoundError(f"截图不存在: {path}")
    im = Image.open(path).convert("RGB")
    if im.width == width:
        return im
    return im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)


def make(day, out_dir, font_path):
    imgs, labels = [], []
    for item in day["images"]:
        imgs.append(load(item["path"], item.get("width", 720)))
        labels.append(item.get("label", ""))

    w = max(i.width for i in imgs)
    body_h = sum(i.height + (LABEL_H if lb else 0) for i, lb in zip(imgs, labels))
    canvas = Image.new("RGB", (w, BANNER_H + body_h), (255, 255, 255))
    d = ImageDraw.Draw(canvas)

    # 顶部横幅
    d.rectangle([0, 0, w, BANNER_H], fill=BG)
    title = day.get("title", "")
    sub = day.get("sub", "")
    tf, _ = fit_text(d, title, font_path, w - 40, 30)
    sf, _ = fit_text(d, sub, font_path, w - 40, 21)
    d.text((20, 14), title, font=tf, fill=FG)
    d.text((20, 58), sub, font=sf, fill=SUB)

    # 分段图 + 段标签
    y = BANNER_H
    lf = font_at(font_path, 18)
    for im, lb in zip(imgs, labels):
        if lb:
            d.rectangle([0, y, w, y + LABEL_H], fill=LABEL_BG)
            d.text((16, y + 7), lb, font=lf, fill=LABEL_FG)
            y += LABEL_H
        canvas.paste(im, ((w - im.width) // 2, y))
        y += im.height

    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, day["file"])
    if out.lower().endswith(".jpg") or out.lower().endswith(".jpeg"):
        canvas.save(out, quality=88)
    else:
        canvas.save(out)
    print("saved", out, canvas.size)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    a = ap.parse_args()

    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)

    out_dir = cfg.get("out_dir", "routes/final")
    font_path = pick_font(cfg.get("font"))
    if font_path is None:
        print("警告：未找到中文字体，横幅中文可能显示为方块")

    failed = 0
    for day in cfg["days"]:
        try:
            make(day, out_dir, font_path)
        except Exception as e:
            failed += 1
            print(f"失败 {day.get('file')}: {e}")

    if failed:
        sys.exit(f"{failed} 个 Day 生成失败，检查配置里的截图路径")


if __name__ == "__main__":
    main()
