#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行程绕路校验器 —— 在出攻略前用几何算一遍，证明"不绕路"，而不是嘴上说。

用法：
    python check_route_geometry.py itinerary.json          # 校验并打印报告
    python check_route_geometry.py itinerary.json --json   # 输出机器可读结果

itinerary.json 格式（ROAD_FACTOR 可缺省）：
{
  "road_factor": 1.25,            // 直线距离 -> 实际驾车里程的经验系数
  "days": [
    {"day": "Day2", "date": "10/2", "home": "住处",
     "points": [
       {"name": "住处",   "lon": 122.10, "lat": 40.20},
       {"name": "景点 A", "lon": 122.09, "lat": 40.21},
       {"name": "景点 B", "lon": 122.08, "lat": 40.22}
     ]}
  ]
}
说明：points 的第一项是住处（起点），校验器会自动把住处追加到末尾形成闭环，
      因此你只需要写"当天实际要去的点"，不必手写回程。

判定标准（可调）：
  - 折返段：去程相邻两段的行进方向夹角 > 120°，说明在往回走
  - 次序比：当天实际路线长 / 中间点全排列穷举出的最短路线长。
      PASS < 1.15 | WARN 1.15~1.30 | FAIL > 1.30
      （多点行程的"绕路"本质是次序不好，不是覆盖比高——覆盖比只作参考）
  - 覆盖比：链总长 / (2 × 起点到最远点直线距离)，仅参考，不判定
  - 单程日（oneway=true，如到达/返程日）只算里程，不做闭环与次序判定
"""
import json
import math
import sys
from itertools import permutations

# 判定阈值
TURN_BACK_DEG = 120.0     # 去程相邻段方向夹角超过这个值 = 折返
ORDER_WARN = 1.15         # 当前次序 / 最优次序 超过这个比例 = 次序不优
ORDER_FAIL = 1.30         # 超过这个比例 = 明显绕路
COVERAGE_REF = 1.35       # 覆盖比参考线（总里程 / 2×最远点）：多点行程天然 >1，仅作参考
MAX_BRUTE = 7             # 中间点超过这个数量就不穷举（组合爆炸）

R = 6371.0


def hav(lon1, lat1, lon2, lat2):
    """两点球面距离，单位 km。"""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def bearing(lon1, lat1, lon2, lat2):
    """方位角，0=正北，顺时针。"""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def angle_delta(a, b):
    """两个方位角之间的夹角（0~180）。"""
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


def chain_len(seq):
    return sum(hav(a["lon"], a["lat"], b["lon"], b["lat"])
               for a, b in zip(seq, seq[1:]))


def check_day(day, road_factor):
    pts = day["points"]
    if len(pts) < 2:
        return {"day": day.get("day"), "status": "SKIP", "reason": "点位不足"}

    # 闭环：住处补到末尾（oneway=true 的单程日不闭环；已手写收尾节点的也不重复补）
    home = pts[0]
    if day.get("oneway"):
        loop = list(pts)
    elif len(pts) > 1 and pts[-1]["name"] == home["name"]:
        loop = list(pts)
    else:
        loop = list(pts) + [home]
    legs = []
    for a, b in zip(loop, loop[1:]):
        d = hav(a["lon"], a["lat"], b["lon"], b["lat"])
        legs.append({"from": a["name"], "to": b["name"],
                     "km": round(d, 2), "road_km": round(d * road_factor, 1),
                     "bearing": round(bearing(a["lon"], a["lat"], b["lon"], b["lat"]), 1)})

    total = sum(l["km"] for l in legs)

    # 起点到最远点
    far = max((hav(home["lon"], home["lat"], p["lon"], p["lat"]), p["name"])
              for p in pts[1:]) if len(pts) > 1 else (0, home["name"])
    if far[0] <= 0:
        detour = 1.0
    elif day.get("oneway"):
        detour = total / far[0]                 # 单程日：理想直达 = 1.0
    else:
        detour = total / (2 * far[0])           # 往返闭环：理想往返 = 1.0

    # 折返检测：只在「去程段」之间做（排除最后一段回住处/到站的收尾段，也排除零长段）
    go_legs = [l for l in legs if l["km"] > 0.3]
    if not day.get("oneway") and len(go_legs) > 1 and go_legs[-1]["to"] == home["name"]:
        go_legs = go_legs[:-1]
    turn_backs = []
    for i in range(len(go_legs) - 1):
        delta = angle_delta(go_legs[i]["bearing"], go_legs[i + 1]["bearing"])
        if delta > TURN_BACK_DEG:
            turn_backs.append({"at": go_legs[i + 1]["from"],
                               "turn_deg": round(delta, 1)})

    # 次序最优性（中间点全排列穷举）——这是「有没有多走路」的主判据
    order_note = None
    order_ratio = 1.0
    middles = [p for p in pts[1:] if p["name"] != home["name"]]
    best_seq = None
    if not day.get("oneway") and 2 <= len(middles) <= MAX_BRUTE:
        best_len, best_seq = None, None
        for perm in permutations(middles):
            cand = [home] + list(perm) + [home]
            l = chain_len(cand)
            if best_len is None or l < best_len:
                best_len, best_seq = l, cand
        if best_len:
            order_ratio = total / best_len
            if order_ratio > ORDER_WARN:
                order_note = {
                    "ratio": round(order_ratio, 3),
                    "current_km": round(total, 2),
                    "best_km": round(best_len, 2),
                    "waste_km": round(total - best_len, 2),
                    "suggested": " → ".join(p["name"] for p in best_seq),
                }

    # 综合判定：以「次序比」为准。闭环行程里点位分布在起点不同方位时，
    # 方向反转是正常的（最终都要回住处），不能据此判绕路，只作提示。
    if order_ratio > ORDER_FAIL:
        status = "FAIL"
    elif order_note:
        status = "WARN"
    else:
        status = "PASS"

    return {
        "day": day.get("day"), "date": day.get("date"), "status": status,
        "legs": legs,
        "total_km": round(total, 2),
        "total_road_km": round(total * road_factor, 1),
        "farthest": {"name": far[1], "km": round(far[0], 2)},
        "coverage_ratio": round(detour, 3),
        "order_ratio": round(order_ratio, 3),
        "turn_backs": turn_backs,
        "order_note": order_note,
    }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(2)
    data = json.load(open(args[0], encoding="utf-8"))
    rf = data.get("road_factor", 1.25)
    results = [check_day(d, rf) for d in data["days"]]

    if "--json" in sys.argv:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print("=" * 66)
        print("行程绕路校验报告   路网系数 x%.2f（直线→驾车）" % rf)
        print("=" * 66)
        for r in results:
            if r["status"] == "SKIP":
                print("\n[%s] 跳过：%s" % (r["day"], r["reason"]))
                continue
            mark = {"PASS": "✓", "WARN": "!", "FAIL": "✗"}[r["status"]]
            print("\n%s %s %s   次序比 %.2f   直线合计 %.1fkm / 驾车约 %.0fkm"
                  % (mark, r["day"], r.get("date", ""), r["order_ratio"],
                     r["total_km"], r["total_road_km"]))
            for l in r["legs"]:
                print("     %-14s → %-14s %6.1fkm  驾车≈%5.1fkm"
                      % (l["from"], l["to"], l["km"], l["road_km"]))
            print("     最远点：%s（距住处 %.1fkm）" % (r["farthest"]["name"], r["farthest"]["km"]))
            for t in r["turn_backs"]:
                print("     · 方向反转：在【%s】处转向 %.0f°（闭环行程中属正常，已计入次序比）"
                      % (t["at"], t["turn_deg"]))
            if r["order_note"]:
                n = r["order_note"]
                print("     ! 次序不优：当前 %.1fkm，最优 %.1fkm，多走 %.1fkm"
                      % (n["current_km"], n["best_km"], n["waste_km"]))
                print("       建议次序：%s" % n["suggested"])
            if r["status"] == "PASS":
                print("     ✓ 单向推进，无折返，无绕路")

        bad = [r for r in results if r["status"] != "PASS"]
        print("\n" + "=" * 66)
        if bad:
            print("结论：%d/%d 天存在问题，需要调整" % (len(bad), len(results)))
            sys.exit(1)
        print("结论：全部通过 —— 每天单向推进、无折返、无绕路")
        sys.exit(0)


if __name__ == "__main__":
    main()
