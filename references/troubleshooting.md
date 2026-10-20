# 实战经验与故障处理

从真实项目里沉淀的坑与处置办法。出图、单文件交付、手册模板三块最常出问题，先看这里。

## 1. 运行环境坑（Windows 实测）

- Bash 环境可能缺 coreutils（`ls`/`tail`/`head`/`dirname` 都没有）→ 用 Python 一行脚本代替 shell 管道，或直接用 PowerShell。
- `pip` 若被锁在不可达镜像源，**显式加 `-i https://pypi.org/simple`**。
- 输出中文别用 PowerShell 捕获（会丢字符），改用 Python subprocess + 显式解码，或**先写文件再读**。
- 无头浏览器可用 `channel="msedge"` 复用本机 Edge，不必下载 Chromium。

## 2. 地图采集

- 带 lnglat 坐标的 `ditu.amap.com/dir` URL 可行，**不需要 POI id**；不带坐标则页面空白停在默认城市。
- `via` 途经点在网页端不支持 → 用 `AMap.Driving` 的 `waypoints` 或 Web 服务 API 的 `waypoints`。
- headless 无 cookie 时高德必弹登录遮罩，截图方案极易失败 → **优先 A 方案（Web 服务 key 纯 HTTP）**，不依赖浏览器。
- 出图后肉眼核对起终点是否落在可辨识地标上，**不核对不算采集完成**。

## 3. 单文件交付

- 相对路径引本地 png，单文件传出去必断图 → base64 `data:` URI 内嵌是唯一正解。7 张 1024×720 的 PNG 约 1.7MB，整份 HTML 可控制在 3MB 内（目标 ≤8MB）。
- 换图技巧：按 `data:image/png;base64` 出现顺序对应 Day1..N，替换前用邻近 `routes/day-DayN.png` 引用做顺序校验，**倒序替换避免位移**。
- PDF：Playwright 打印时注入 print CSS 覆盖 `break-inside` 并强制展开 `details`，否则折叠内容被吞或留大片空白。
- 校验三连：`src="data:image` 数量 = 图数、`src="http` = 0、`<img` 数量 = 图数。

## 4. 手册模板

- 窄屏（≤760px）路线图自动转竖排，保证「回住处/到家」末端节点不被横向滚动藏掉；单天节点数建议 ≤5。
- 「今天自动定位」按 `details[data-date]` 比对当前日期自动展开 + 滚到当日。
- 无 JS 环境（部分阅读器）退化为静态文档，内容无损但交互失效——设计上已保证。

## 5. 高德 API 错误码速查

| 码 | 含义 | 处置 |
|---|---|---|
| 10009 | USERKEY_PLAT_NOMATCH | key 类型选错了，必须是「Web服务」，不是「Web端(JS)」 |
| 10021 | 并发超限 | 稍等重试；脚本已内置 `sleep(1.1)` 避让 |
| 20000 | staticmap 参数错误（如 labels 段数过多） | `labels` 参数不可用，改用 Pillow 本地绘图 |
