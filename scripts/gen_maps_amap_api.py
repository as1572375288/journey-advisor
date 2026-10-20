# -*- coding: utf-8 -*-
"""
Journey Advisor · 途顾问 — A 方案：用高德「Web服务」key 纯 HTTP 生成每日真实路线图（不需要浏览器）。

用法：
  python gen_maps_amap_api.py --base <输出目录> --key <你的Web服务key>
  python gen_maps_amap_api.py --base <输出目录>            # 从环境变量 AMAP_WEB_KEY 读取

数据契约：脚本读取 <输出目录>/itinerary.json，结构为：
{
  "days": [
    {
      "day": "Day1",
      "date": "10/1",
      "theme": "到达日 · 站 → 住处",
      "points": [
        {"name": "住处",   "lon": 122.10, "lat": 40.20},
        {"name": "景点 A", "lon": 122.09, "lat": 40.21}
      ]
    }
  ]
}
闭环规则：points[0] 与 points[-1] 同为住处即闭环；首末日为「站 ↔ 住处」。
坐标必须权威且复核（禁止手工估算——高德对任何坐标都会算出「合法」读数，有读数 ≠ 坐标对）。

流程（每天一条链）：
  1) direction/driving —— 起点 + 途经点 + 终点一次算完整条链，拿 distance/duration/polyline
  2) staticmap         —— 真实底图 + paths(真实路线) + markers(起点绿/途经橙/终点红)
  3) Pillow            —— 叠加中文标题条、里程读数、图例（staticmap 的 labels 参数不可用，改用本地绘制）
输出：<输出目录>/routes/day-DayN.png 与 <输出目录>/routes/_daymaps_api.json

key 获取（重要）：
  去 https://lbs.amap.com 控制台 → 创建应用 → 添加 key，服务平台必须选「Web服务」。
  「Web端(JS)」key 调 restapi.amap.com 会返 10009 USERKEY_PLAT_NOMATCH。
  本脚本不内置任何 key——谁用谁传自己的（--key 参数或环境变量 AMAP_WEB_KEY）。
"""
import argparse, io, json, math, os, sys, time, urllib.parse, urllib.request
from PIL import Image, ImageDraw, ImageFont

API = 'https://restapi.amap.com/v3'

FONT_CANDIDATES = ['C:/Windows/Fonts/msyhbd.ttc', 'C:/Windows/Fonts/msyh.ttc',
                   '/System/Library/Fonts/PingFang.ttc',
                   '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                   '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc']


def font(size, bold=False):
    cands = FONT_CANDIDATES if bold else FONT_CANDIDATES[1:] + FONT_CANDIDATES[:1]
    for fp in cands:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': 'journey-advisor/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def api_json(url):
    d = json.loads(http_get(url).decode('utf-8', 'ignore'))
    if d.get('status') != '1':
        code, info = d.get('infocode'), d.get('info')
        if code == '10009':
            raise SystemExit('key 平台不匹配（10009）→ 请改用「Web服务」类型的 key（不是 Web端(JS)）')
        if code == '10021':
            raise SystemExit('并发超限（10021）→ 稍等几秒重试')
        raise SystemExit('高德接口失败: %s %s' % (code, info))
    return d


def driving(key, origin, destination, waypoints, strategy=10):
    p = {'key': key, 'origin': origin, 'destination': destination,
         'strategy': strategy, 'extensions': 'all', 'output': 'JSON'}
    if waypoints:
        p['waypoints'] = ';'.join(waypoints)
    d = api_json(API + '/direction/driving?' + urllib.parse.urlencode(p))
    path = d['route']['paths'][0]
    km = round(int(path['distance']) / 1000.0, 1)
    minute = int(round(int(path['duration']) / 60.0))
    pts = []
    for st in path.get('steps', []):
        for seg in st.get('polyline', '').split(';'):
            if seg:
                pts.append(seg)
    return km, minute, pts


def thin(pts, maxn=80):
    if len(pts) <= maxn:
        return pts
    step = (len(pts) - 1) / float(maxn - 1)
    idx = sorted(set([int(round(i * step)) for i in range(maxn)] + [len(pts) - 1]))
    return [pts[i] for i in idx]


def bbox_of(points):
    lngs, lats = [], []
    for p in points:
        lng, lat = p.split(',')
        lngs.append(float(lng)); lats.append(float(lat))
    return min(lngs), max(lngs), min(lats), max(lats)


def auto_zoom(box, w, h, lat_center):
    minlng, maxlng, minlat, maxlat = box
    coslat = math.cos(math.radians(lat_center))
    w_m = max((maxlng - minlng) * 111320.0 * coslat, 1.0) * 1.5
    h_m = max((maxlat - minlat) * 110540.0, 1.0) * 1.5
    z = 17
    while z > 6:
        tile = 156543.03392 * coslat / (2 ** z)
        if tile * w >= w_m and tile * h >= h_m:
            break
        z -= 1
    return z


def marker_str(coords):
    out, letters = [], 'ABCDEFGH'
    for i, c in enumerate(coords):
        if i == 0:
            out.append('large,0x0f9d58,%s:%s' % (letters[0], c))
        elif i == len(coords) - 1:
            out.append('large,0xea4335,%s:%s' % (letters[i % 8], c))
        else:
            out.append('mid,0xf9ab00,%s:%s' % (letters[i % 8], c))
    return '|'.join(out)


def staticmap(key, pts, marks, size='1024*720'):
    minlng, maxlng, minlat, maxlat = bbox_of(pts)
    lat_c = (minlat + maxlat) / 2.0
    lng_c = (minlng + maxlng) / 2.0
    w, h = (int(x) for x in size.split('*'))
    zoom = auto_zoom((minlng, maxlng, minlat, maxlat), w, h, lat_c)
    p = {'key': key,
         'location': '%.6f,%.6f' % (lng_c, lat_c),
         'zoom': zoom, 'size': size, 'scale': 1,
         'paths': '8,0x1565c0,1,,:' + ';'.join(thin(pts))}
    if marks:
        p['markers'] = marks
    data = http_get(API + '/staticmap?' + urllib.parse.urlencode(p))
    if len(data) < 1024 and data[:1] == b'{':
        raise SystemExit('staticmap 错误: ' + data.decode('utf-8', 'ignore')[:200])
    return data, zoom


def overlay(png_bytes, tag, title, subtitle, names, km, minute):
    """叠加中文标题条、读数条与图例"""
    im = Image.open(io.BytesIO(png_bytes)).convert('RGB')
    W, H = im.size
    d = ImageDraw.Draw(im)

    def bar(y0, y1, alpha=205):
        layer = Image.new('RGBA', (W, y1 - y0), (16, 28, 48, alpha))
        im.paste(Image.alpha_composite(im.crop((0, y0, W, y1)).convert('RGBA'), layer)
                 .convert('RGB'), (0, y0))

    # 顶部条
    top_h = 96
    bar(0, top_h)
    d.rectangle([0, top_h - 3, W, top_h], fill=(255, 138, 76))
    f_title = font(30, True)
    f_sub = font(17)
    d.text((22, 14), '%s · %s' % (tag, title), font=f_title, fill=(255, 255, 255))
    d.text((22, 54), subtitle, font=f_sub, fill=(200, 214, 232))

    # 右侧读数
    f_num = font(24, True)
    txt = '全程 %.1f km / 约 %d min' % (km, minute)
    tw = d.textlength(txt, font=f_num)
    d.text((W - tw - 22, 20), txt, font=f_num, fill=(255, 208, 138))

    # 底部图例
    legend = ' ⇢ '.join('%s %s' % ('ABCDEFGH'[i], n) for i, n in enumerate(names))
    f_leg = font(16)
    bot_h = 74
    # 自适应：图例过长则缩小字号
    while d.textlength(legend, font=f_leg) > W - 44 and f_leg.size > 11:
        f_leg = font(f_leg.size - 1)
    bar(H - bot_h, H)
    d.text((22, H - bot_h + 12), legend, font=f_leg, fill=(255, 255, 255))
    f_src = font(13)
    d.text((22, H - 26), '高德地图真实底图与驾车路线 · 全天途经点一张图 · 闭环回到住处',
           font=f_src, fill=(150, 168, 190))

    out = io.BytesIO()
    im.save(out, 'PNG')
    return out.getvalue()


def main():
    ap = argparse.ArgumentParser(description='Journey Advisor A 方案：纯 HTTP 生成每日真实路线图')
    ap.add_argument('--base', default=os.getcwd(),
                    help='输出目录（含 itinerary.json，routes/ 将建在其下），默认当前目录')
    ap.add_argument('--itin', default='', help='itinerary.json 路径，默认 <base>/itinerary.json')
    ap.add_argument('--key', default=os.environ.get('AMAP_WEB_KEY', ''),
                    help='高德 Web服务 key；也可用环境变量 AMAP_WEB_KEY')
    ap.add_argument('--days', default='', help='只跑指定天，如 Day2,Day4；默认全部')
    ap.add_argument('--size', default='1024*720')
    args = ap.parse_args()
    if not args.key:
        raise SystemExit('需要高德 Web服务 key：--key <key> 或环境变量 AMAP_WEB_KEY（本脚本不内置 key）')

    itin_path = args.itin or os.path.join(args.base, 'itinerary.json')
    outdir = os.path.join(args.base, 'routes')
    meta = os.path.join(outdir, '_daymaps_api.json')

    itin = json.load(io.open(itin_path, encoding='utf-8'))
    os.makedirs(outdir, exist_ok=True)
    results = []

    for day in itin['days']:
        tag = day['day']
        if args.days and tag not in args.days.split(','):
            continue
        coord = ['%.6f,%.6f' % (p['lon'], p['lat']) for p in day['points']]
        names = [p['name'] for p in day['points']]
        km, minute, poly = driving(args.key, coord[0], coord[-1], coord[1:-1])
        if not poly:
            print('%s 无 polyline，跳过' % tag)
            continue
        png, zoom = staticmap(args.key, poly, marker_str(coord), size=args.size)
        png = overlay(png, tag, day.get('theme', '当日路线'),
                      '%s · 起点终点均为住处（闭环）' % day['date'], names, km, minute)
        fp = os.path.join(outdir, 'day-%s.png' % tag)
        open(fp, 'wb').write(png)
        results.append({'day': tag, 'date': day['date'], 'file': fp,
                        'km': km, 'min': minute, 'zoom': zoom, 'chain': names})
        print('%s %s  %.1fkm / %dmin  zoom=%d  %d KB'
              % (tag, day['date'], km, minute, zoom, len(png) // 1024))
        time.sleep(1.1)   # 避开 10021 并发限制

    io.open(meta, 'w', encoding='utf-8').write(json.dumps(results, ensure_ascii=False, indent=2))
    print('\n共 %d 张 -> %s' % (len(results), meta))


if __name__ == '__main__':
    main()
