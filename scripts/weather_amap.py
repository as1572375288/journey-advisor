#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weather_amap.py —— 用高德 Web 服务 key 查天气（「事实数据」里的气象源）

为什么要有这个脚本
------------------
天气网/墨迹的 15–40 天预报，长期段本质是气候统计推算，越往后越不准。
高德天气 API 的数据来自中国气象局，**实测比长期预报准得多**，是事实核验的首选气象源。

但有一个必须知道的限制（别拿它当万能）：
------------------------------------------
`extensions=all` 只返回 **今天 + 未来 3 天**，一共 4 天。
也就是说：9/27 查，最多看到 9/30；国庆 10/1–10/6 的天气它**看不到**。

正确用法是「滚动补查」，不是一次查完：
    出发前 3–4 天  → 查一次，覆盖到达日附近
    行程中每天     → 再查一次，滚动覆盖后续 3 天
    4 天以外的日期 → 仍用预报源（中国天气网 / ECMWF / GFS），标 `参考` 并列入复查清单

四个源怎么分工、怎么采信、站点代码怎么找（别凭记忆写，容易查到另一个城市），
见 references/weather-sourcing.md —— **查天气前必读**。

脚本会把「哪天是实查、哪天是预报」直接标进输出，避免混淆。

USAGE
    python weather_amap.py --city 营口 --key <你的高德Web服务key>
    python weather_amap.py --city 210800 --key <key> --out weather.json

EXIT CODES
    0  成功
    2  缺少 --key 或 --city
    3  API 返回失败（含 10009 平台不匹配等，会给出人话提示）
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request

API = "https://restapi.amap.com/v3/weather/weatherInfo"

# 高德天气常见错误码 → 人话（和 gen_maps_amap_api.py 保持一致，别只丢一个码给用户）
ERR_HINT = {
    "10001": "key 不正确或已过期",
    "10002": "没有权限使用这个服务（key 未开通天气服务）",
    "10003": "访问已超出日配额",
    "10009": "key 与调用平台不匹配 —— 必须用「Web服务」类型的 key，不是「Web端(JS)」",
    "10021": "并发超限，稍等几秒再试",
    "20000": "请求参数非法（多半是 city 写错）",
    "20011": "查询不到该城市的天气（city 用中文名或 adcode，如「营口」或 210800）",
    "30001": "服务响应异常，重试一次",
}


def fetch(city, key, extensions="all"):
    qs = urllib.parse.urlencode({
        "city": city, "key": key, "extensions": extensions, "output": "JSON",
    })
    url = "%s?%s" % (API, qs)
    req = urllib.request.Request(url, headers={"User-Agent": "journey-advisor/1.2"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def fmt_forecast(data):
    """把高德返回整理成人能读的表，并区分『实查』与『超出覆盖范围』。"""
    lines = []
    city = data.get("city") or data.get("province") or ""
    lines.append("城市: %s（高德 · 中国气象局数据）" % city)
    lines.append("说明: extensions=all 仅覆盖【今天 + 未来 3 天】，再往后查不到，需滚动补查")
    lines.append("")

    casts = (data.get("forecasts") or [{}])[0].get("casts") or []
    if not casts:
        return "未返回预报数据（city 是否正确？）"

    lines.append("| 日期 | 星期 | 白天 | 夜间 | 高温 | 低温 | 风向 | 风力 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for c in casts:
        lines.append("| %s | 周%s | %s | %s | %s℃ | %s℃ | %s | %s |" % (
            c.get("date"), c.get("week"), c.get("dayweather"), c.get("nightweather"),
            c.get("daytemp"), c.get("nighttemp"),
            c.get("daywind"), c.get("daypower"),
        ))
    lines.append("")
    lines.append("标注写法：以上日期可标 `实查 · <查询日期> · 高德气象`")
    lines.append("超出这 %d 天的行程日期：用预报源（中国天气网/墨迹）标 `参考`，并列入出发前复查清单。" % len(casts))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="高德天气查询（事实核验首选气象源，仅覆盖今天+未来3天）")
    ap.add_argument("--city", required=True, help="城市中文名或 adcode，如 营口 / 210800")
    ap.add_argument("--key", required=True, help="高德 Web 服务 key（谁用谁传，脚本不内置）")
    ap.add_argument("--extensions", default="all", choices=["all", "base"],
                    help="all=预报(今天+3天)，base=当日实况")
    ap.add_argument("--out", default=None, help="同时把原始 JSON 存到这个文件")
    args = ap.parse_args()

    if not args.key or not args.city:
        print("[weather] 缺 --city 或 --key", file=sys.stderr)
        return 2

    data = fetch(args.city, args.key, args.extensions)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    if str(data.get("status")) != "1":
        code = str(data.get("infocode") or data.get("errcode") or "")
        hint = ERR_HINT.get(code, data.get("info") or data.get("errmsg") or "未知错误")
        print("[weather] 失败 infocode=%s %s" % (code, hint), file=sys.stderr)
        return 3

    if args.extensions == "base":
        lives = (data.get("lives") or [{}])[0]
        print("实况 %s：%s %s℃ 湿度%s%% %s风%s级（%s 更新）" % (
            lives.get("city"), lives.get("weather"), lives.get("temperature"),
            lives.get("humidity"), lives.get("winddirection"), lives.get("windpower"),
            lives.get("reporttime"),
        ))
    else:
        print(fmt_forecast(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
