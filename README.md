# Journey Advisor · 途顾问

中文旅行攻略生成器，一个 [WorkBuddy](https://www.workbuddy.cn) 技能（Skill）。

输入「目的地 + 日期 + 天数 + 预算 + 偏好」，它会走一套固定工作流，产出一份**事实实查、带真实地图路线图**的旅行攻略，并在交付前先问你选哪种形态。

> 本仓库**不内置任何 API key**。地图与天气所需的高德「Web 服务」key 由使用者自行申请并传入（见下方「配置」）。

---

## 功能特性

- **八模块攻略**：行程总览、每日路线、交通、住宿、美食、景点避雷、预算、应急联络，一次成型。
- **三种交付形态**（交付前会先问你选哪种，只做选定的那一种）：
  1. 飞书在线文档（首选，便于分享与协作）；
  2. 单文件自包含 HTML 手册（地图 base64 内嵌，离线可用、手机友好）；
  3. PDF。
- **六大纪律**：
   - 一次一问确认需求，到高置信度才出方案；
   - 事实实查 + 三色标注（已核实 / 参考 / 待核实）；
   - 舆情反查避雷 + 本地推荐（不只查官方，也看小红书 / 携程 / 大众点评）；
   - 顺路最短不回头；
   - 一日自足按天聚合；
   - 每日一张单图闭环真实路线图。
- **绝不凭记忆写票价 / 天气 / 潮汐 / 开放时间**；境外服务（Google Maps、OpenStreetMap 等）一律不用，地图只用高德、百度、腾讯。

---

## 安装（作为 WorkBuddy 技能）

把本仓库放到 WorkBuddy 的技能目录下即可，二选一：

```bash
# 方式 A：用户级技能目录
git clone <本仓库地址> "$HOME/.workbuddy/skills/journey-advisor"

# 方式 B：项目级技能目录
git clone <本仓库地址> "<你的项目>/.workbuddy/skills/journey-advisor"
```

重启 / 刷新 WorkBuddy 后，在对话里用自然语言触发即可，例如：

- 「帮我做一份 成都 周末 2 天 预算 2000 的美食攻略」
- 「东京 7 天自由行，带爸妈，要温泉」
- 「三亚 vs 万宁 哪个更适合带娃，先出对比表」

---

## 配置

### 高德「Web 服务」key（出真实路线图 / 查天气时需要）

1. 到 [高德开放平台控制台](https://lbs.amap.com) → 创建应用 → 添加 key；
2. **服务平台必须选「Web 服务」**（选「Web端(JS)」调 `restapi.amap.com` 会返回 `10009 USERKEY_PLAT_NOMATCH`）；
3. 传入方式二选一：
   - 环境变量：`export AMAP_WEB_KEY="你的key"`
   - 命令行参数：`python scripts/gen_maps_amap_api.py --key 你的key --base 输出目录`

> 不配置也能用——只是地图路线图会降级为「高德 URI 导航链接 + 文字路线」，不影响其余攻略内容。

### 飞书在线文档（可选，仅当你要「飞书文档」这种交付形态）

需要安装飞书 `lark-cli` 并登录。详见 `references/online-doc-delivery.md`（其中 npm 缓存请指向你自己的用户目录，不要照抄示例里的路径）。

---

## 目录结构

```
journey-advisor/
├── SKILL.md                      # 技能主说明（工作流 + 六大纪律 + 配置）
├── LICENSE.txt                   # MIT
├── assets/
│   └── travel-handbook.html      # 单文件 HTML 手册模板（地图 base64 内嵌）
├── evals/
│   └── evals.json                # 技能自测集
├── references/                   # 各模块实操手册
│   ├── content-modules.md        # 八模块内容规范
│   ├── map-screenshots.md        # 真实地图截图 / Web 服务出图
│   ├── weather-sourcing.md       # 天气事实核验口径
│   ├── sentiment-mining.md       # 舆情反查避雷
│   ├── online-doc-delivery.md    # 飞书在线文档交付
│   ├── local-delivery.md         # 本地 HTML / PDF 交付
│   ├── validation.md             # 验收标准
│   └── troubleshooting.md        # 常见报错与处置
└── scripts/                      # 出图 / 天气 / 文档转换等辅助脚本
    ├── gen_maps_amap_api.py      # A 方案：高德 Web 服务 key 纯 HTTP 出每日单图
    ├── weather_amap.py           # 高德天气查询
    ├── make_route_maps.py        # 路线截图拼图
    ├── build_handbook.py         # 组装 HTML 手册
    ├── export_pdf.py             # 导出 PDF
    ├── check_handbook_render.py  # 渲染自检
    ├── check_route_geometry.py   # 路线几何校验
    └── md_to_feishu_xml.py       # Markdown → 飞书文档 XML
```

---

## 许可证

[MIT](./LICENSE.txt) — 署名 "Journey Advisor · 途顾问 contributors"。
