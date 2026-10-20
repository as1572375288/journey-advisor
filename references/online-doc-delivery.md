# 在线文档交付规范（**飞书首选**，腾讯文档备选）

> 载体优先级：**① 飞书（lark-unified 技能 / `lark-cli`）** → ② 腾讯文档 → ③ 本地三件套保底。
> 飞书不可用时不要卡住交付，按 §5 降级。

## 1. 飞书（首选）

### 1.1 用哪个技能

`lark-unified`（飞书套件）——封装官方 `lark-cli`，覆盖 18 个业务域。
注意：**飞书协作（本文档用这个）** 与 **飞书项目 / Meegle** 是两套产品、两个二进制，不要混用。
我们只用到「云文档 docx」，属于飞书协作。

### 1.2 Preflight（每次先跑）

```bash
STATUS=$(find ~/.workbuddy/skills ./.workbuddy/skills -name lark_status.py 2>/dev/null | head -1)
python3 "$STATUS" --json; echo "exit=$?"
```

| 退出码 | 状态 | 处置 |
|---|---|---|
| 0 | 已配置可用 | 直接创建文档 |
| 3 | 未安装 CLI | `npx -y @larksuite/cli@latest install`（数分钟） |
| 4 | 已装未配置 | `python3 lark_setup.py`（设备码流，不开浏览器用 `--print-url-only`） |
| 5 | 输出无法解析 | 手工看 `lark-cli config show` |

### 1.3 创建文档

**短文档**直接带内容创建：

```bash
lark-cli docs +create --doc-format markdown --as user \
  --content $'<title>带爸妈游{目的地}的6天温泉赶海手册</title>\n# 正文…'
```

**长文档（攻略通常都是）用文件导入**——避免命令行参数长度限制：

```bash
lark-cli drive +import --as user --type docx \
  --file <相对路径>.md --name "带爸妈游{目的地}的6天温泉赶海手册"
```

⚠️ **只接受相对路径**（绝对路径会被拒：`unsafe output path`）。先 `cd` 到文件所在目录再执行。
⚠️ **`--type` 是必填**，漏了报 `required flag(s) "type" not set`（退出码 2）。攻略一律 `--type docx`。

成功返回里 **`data.url` 就是最终链接**，直接给用户，不用二次拼接：

```json
{"ok":true,"data":{"token":"OFvqd…","type":"docx","url":"https://my.feishu.cn/docx/OFvqd…","job_status":0}}
```

**导入后必做校验**（别以为 `ok:true` 就完事，导入是异步 job）：

```bash
lark-cli docs +fetch --as user --doc <token> --scope outline --doc-format markdown
```

看 `content` 里的标题树是否完整。注意是 **`--doc`**，不是 `--token`（`docs +fetch` 没有 `--token` 这个 flag）。

### 1.4 最小权限（不要一把梭）

| 动作 | scopes |
|---|---|
| 创建 docx | `docx:document:create` |
| 读取 docx | `docx:document:readonly` |
| 导入/上传文件 | `drive:file:upload` + `drive:file:import` |

```bash
lark-cli auth check --scope "docx:document:create" --json; echo "rc=$?"   # 0=已有，1=缺失
lark-cli auth login --scope "docx:document:create" --no-wait --json        # 缺什么补什么
```

**绝不用 `--domain all` / `--recommend`**（后者含 310 个 scope、13 个删除权限）。
**身份必须显式 `--as user`**：个人云盘/文档只有 user 身份可见，bot 会读到自己的空资源。
缺权限报错带 `missing_scopes`：bot 身份把 `console_url` 交给用户去控制台开；user 身份只补 `missing_scopes` 里那几个。

### 1.5 坑

- 写操作先 `--dry-run` 预览；高危写会退出码 **10**（待确认），确认后加 `--yes` 重跑，**不要自己默默加**。
- 判断成败看 `ok == true` 或退出码，**没有顶层 `code == 0`** 这回事。
- 交互命令（`config init`）在本环境会渲染坏二维码/卡住，改用 `lark_setup.py`。
- 授权 URL 要「先给链接、结束本轮」，不要在同一轮里又给链接又轮询。

### 1.6 Windows 环境实战（本环境已验证 2026-09-23）

这一节是踩过的坑，按顺序照做即可，别再自己摸索一遍。

**① 装 CLI：npm 缓存要先改道**
默认 npm 缓存目录（如系统盘下的 `node_cache`）会报 **EPERM**（权限不足/被占用）。先改两个环境变量，把缓存与全局装到用户目录下（下面用 `$HOME`，Windows Git Bash 中等同于用户目录；PowerShell 请用 `$env:USERPROFILE`）：

```bash
export npm_config_cache="$HOME/.npm-cache"
export npm_config_prefix="$HOME/.npm-global"
npx -y @larksuite/cli@latest install
```

**② 包装完 ≠ 能用：二进制是第二步下载的**
`npx install` 跑的是 postinstall，而 `scripts/install.js` 里有一句：
`npm_command === "exec" && !LARK_CLI_RUN` 时**直接 exit 0，不下载二进制**。
所以 `bin/` 是空的，此时 `lark-cli --version` 必挂。补跑一次（约 2 分钟，走 GitHub→npmmirror 三级回退，别打断）：

```bash
cd <prefix>/node_modules/@larksuite/cli
LARK_CLI_RUN=1 node scripts/install.js     # 成功打印 "lark-cli vX.Y.Z installed successfully"
```

**③ 别信 `lark_status.py` 的 exit 3**
在 Windows 上它会误报 `installed:true / state:not_installed`。原因：npm 生成的 `lark-cli` 是**无扩展名的 sh**，Python `subprocess.run(["lark-cli"])` 走 CreateProcess 只补 `.exe`，找不到就抛 `FileNotFoundError`，脚本把 127 当成「未安装」。
**绕过办法：在 Git Bash 里跑 `lark-cli`**（sh 会被正常解释），不要走 Python subprocess。判断装好没，直接看：

```bash
export PATH="$HOME/.npm-global:$PATH"
export LARKSUITE_CLI_NO_UPDATE_NOTIFIER=1 LARKSUITE_CLI_NO_SKILLS_NOTIFIER=1
lark-cli --version          # → lark-cli version X.Y.Z
lark-cli config show        # → 有 appId / users 即已配置
lark-cli auth status --json # → identities.user.tokenStatus == "valid"
```

**④ 导入一定加 `--as user`**：个人云盘只有 user 身份可见，bot 读到的是自己的空资源。

### 1.7 排版美化：把网页的卡片感搬进飞书

飞书不吃 CSS，但**不是只能交一篇纯文本**。实测一份公认「排版好看」的飞书攻略，
把它拆开数了一下块构成，规律很清楚：

| 它有的 | 数量 | 我们没有的（导入 md 后的样子） |
|---|---|---|
| `callout` 高亮块（带 emoji） | **23** | 0（md 的 `>` 只会变成灰色竖线 blockquote） |
| `grid` 分栏 | 3 | 0 |
| `table`（表头浅灰底） | 10 | 有，但表头没底色 |
| 标题**只用 h2** | 13 | 有 h2+h3，但带「模块 N：」机械编号 |
| `h1` | **0** | 有（重复） |

> 表头底色参考文档用的是 `light-gray` —— 我们改成 `light-blue`，为的是和网页版的「海蓝主色贯穿」对齐（callout 的蓝、表头的蓝、导航的蓝同源）。这是**有意的偏移**，不是抄漏。

**五条可直接抄的规律**：

1. **要点进高亮块，不要散在段落里。** 这是「好看」的第一来源。一个高亮块 = 一张网页卡片。
2. **语义段落自动升级为卡片。** 段落以 `**标签**：` 开头且标签命中语义（避雷 / 预算 / 老人提示 / 交通…）→ 自动转成带色高亮块。**这是块数从个位数涨到几十的关键**（鲅鱼圈手册：9 → 51）。
3. **标题带结论，不要机械编号。** `每天怎么玩：Day 3 环线日——大潮赶海 + 北海团山` ≫ `模块 4：每日行程`。
4. **首屏要点用 grid 两栏并排**，视觉上立刻有「Hero」的感觉。
5. **表头给 `light-blue` 底色**（对齐网页的「海蓝主色贯穿」），表格立刻从"纯文本网格"变成"表"；配色与 callout 的蓝色语义一致。

**别过度压平层级**：上面那份只有 13 个 h2，是因为它结构本来就浅（6 天 + 7 个专题）。
把一篇 38 个小节的攻略全压成 h2，导航会变成一锅粥——**保留 h2/h3 两级，只去掉机械编号**。

**怎么落地**（脚本已封装，别手写 XML）：

```bash
python scripts/md_to_feishu_xml.py --md 攻略.md --maps routes/ --map-prefix routes --out 飞书.xml
cd <routes 所在的目录>          # 图片相对路径以 lark-cli 工作目录为准
lark-cli docs +create --as user --doc-format xml --content @飞书.xml
# 已有文档要改版：
lark-cli docs +update --as user --doc <token> --command overwrite --doc-format xml --content @飞书.xml
```

高亮块配色规则（脚本内置，别自己乱配色）。**两级判定**：先看文本/标签**开头是不是 emoji**（`tone_by_leading_emoji`，命中即用它的色调），否则再按关键词匹配。

**A 组 · 高亮块/引用块关键词**（`CALLOUT_RULES`）：

| 内容特征 | emoji | 底色 |
|---|---|---|
| 避坑 / 套路 / 不要 / 宰客 | 🛑 | `light-red` |
| 注意 / 复查 / 可能 / 限流 | ⚠️ | `light-orange` |
| 预算 / 价格 / ¥ | 💰 | `light-green` |
| 温泉 / 赶海 / 潮汐 / 退潮 | ♨️ 🦀 | `light-blue` |
| 吃 / 餐 / 市场 / 人均 | 🍽 | `light-green` |
| 交通 / 车次 / 停车 | 🚗 | `light-purple` |
| 穿搭 / 装备 / 证件 | 🧥 | `light-yellow` |
| 关键结论 / 重点 | 🎯 | `medium-blue` |
| 已订 / 已核查 | ✅ | `light-green` |

**B 组 · 段落标签自动上色**（`PARA_CALLOUT_RULES`，匹配 `**标签**：` 里的标签）：

| 标签关键词 | emoji | 底色 |
|---|---|---|
| 避雷 / 最大风险 / 风险 | 🛑 | `light-red` |
| 重要调整 / 注意 / 警惕 / 待复查 | ⚠️ | `light-orange` |
| 交通提示 / 今日交通 | 🚗 | `light-purple` |
| 一句话 / 怎么玩 / 核心 / 结论 | 🎯 | `light-blue` |
| 给谁做 / 行程骨架 / 方位 | 👥 🧭 | `light-blue` |
| 预算小计 / 今日预算 / 总账 / 人均 | 💰 | `light-green` |
| 老人提示 | 👵 | `light-yellow` |

**两条硬约束（踩过坑）**：

1. **标签行必须独立成行**（`**⚠️ 今日避雷**：` 单独一行、正文在下一段）。
   若写成「标签行紧邻另一标签行、中间无空行」，解析器会把四行合成一段，**只有第一个标签的颜色生效，后面的避雷直接消失**。
   解析器已加 `_LABEL_LINE` 切分（遇到 `**标签**：` 起新段）兜底，但**写作时仍应保持标签独立成行**，最稳。
2. **标签后无正文的不升级**（`pick_para_callout` 的空卡片防护）。
   `**⚠️ 今日避雷**：` 后面直接跟有序列表 → 会产生**空的红卡片**。正确写法是把要点写进同一段（`**⚠️ 今日避雷**：① … ② …`），或删掉这个裸标签。

**验收**：`docs +fetch --scope full --doc-format xml` 数一遍，
`blockquote` 应该为 0（全部转成了 callout），`callout` ≥ 10，`img` 数量 = 路线图张数，
且**没有内容为空的 callout**（`<callout …><p></p></callout>` 或只有标签的）。

> ⚠️ **fetch 回读不保留表头底色**：回读时表头会被归一化成 `<th vertical-align="top">`，`background-color` 属性**消失**——这是回读归一化，**不代表底色没生效**。
> **表头配色只能看写入口判定**（`docs +script --command parse` 返回 `ok`、零 error/warning），别拿 fetch 的结果判定，否则会误以为没上色而白折腾一轮。

## 2. 腾讯文档（备选）

| 账号 | 技能 | 域名 |
|---|---|---|
| 个人 QQ / 微信 | `tencent-docs` | docs.qq.com |
| 企业版（SaaS / OneID） | `tencent-saas-docs` | saas.docs.qq.com |

判断法：直接加载 `tencent-docs`，返回 `ERROR:identity_mismatch` 则改企业版，**不靠猜**。
创建方式：智能文档（smartcanvas）的 MDX/Markdown 接口（如 `create_smartcanvas_by_mdx`），MDX 向下兼容全部 Markdown。
**不要「上传本地 HTML」生成正文**，会丢排版结构。

## 3. 标题与正文结构（两种载体通用）

标题：`带{人群}游{目的地}的{天数}天{主题}手册`

正文按八模块，其中**每日行程必须自足**（见 `content-modules.md` 一日自足原则）：

```markdown
# 带{人群}游{目的地}的{天数}天{主题}手册
> 一句话怎么玩：{...}。最大风险：{...}。

## 一、天气与穿搭
| 日期 | 天气 | 气温 | 对行程影响 |

## 二、路线总览
| 日期 | 主区域 | 核心安排 | 风险 |

## 三、每日行程（每一节自足：不看别处也能走完这天）
### Day 1 · {日期} · {主区域}
**今日主线**：{...}
![Day1 全天路线](图片)
| 时间 | 安排 | 怎么去 / 费用 | 说明 |
**今日三餐**：早餐｜{店名 · 人均 · 时段}；午餐｜{...}；晚餐｜{...}
**今日预算小计**：人均 ¥{...}
**今日避雷**：{当天才涉及的坑}
**今日强度**：步行约 { } km / 连续户外 { } 小时
**今日预订提醒**：{需提前 N 天订的}
🗑️ 可删减：{...}　🔄 备选：{...}

## 四、跨天交通与预订
## 五、主题玩法速查 + 避雷全览 + 安全卡
## 六、预算账本（总账）
## 七、出发前时间线
## 八、变化应对 Q&A
```

## 4. 图片插入（必须串行）

1. **一张一张串行上传并插入，严禁并行**——并行会丢图且不报错。
2. 插完拉全文核对图片数量与所属章节，确保每张都在对应 Day 下。
3. 图片标题写清：`Day1 全天路线（高德真实地图）`。
4. 图片来自 `final-DayN.png`（真实截图）或 `routes/day-DayN.png`（A 方案出图）。

## 5. 降级与一致性

- 两个在线产物与本地三件套**共用同一套数据**，先定数据再分别渲染；一边改了另一边必须同步。
- 在线文档不可用（未授权 / 接口报错）时：**明确告知未生成，不要假装成功** → HTML 手册照常交付（离线可用）→ Markdown 源文件落盘，用户可自行导入。
- 交付前对照「双形态内容一致」一项。

## 6. 禁止

- 禁止编造文档链接。
- 禁止把 CLI 命令、内部字段名、工具名写进正文。
- 禁止使用平台不支持的语法（以对应 skill 文档为准）。
