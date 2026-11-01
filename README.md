# 广告拦截域名列表（自动构建 · 含白名单）

一个跑在 GitHub 上的自动化方案：**抓取 → 合并 → 按"跨列表出现频次"优选 → 数量封顶**，
产出两个文件并持续保持最新：

- **`lists/domains.txt`** — 拦截列表（单行一个精确域名）
- **`lists/whitelist.txt`** — 白名单（永不拦截的域名）

> 核心思想：不追求"域名越多越好"，而是**只保留被多个权威源共同确认的、最常见的广告/追踪域名**，
<<<<<<< HEAD
> 数量可控（默认封顶 300000 条，即 1000×300，作为完整下载文件）。
> 本仓库**不做任何上传/同步**，只负责生成文件并提供随时可用的下载链接。
>
> ⚠️ **关于 Cloudflare Gateway 单列表上限**：根据官方文档，Cloudflare Gateway 单个列表上限为
> **Standard 1000 条 / Enterprise 5000 条**，且上传 CSV 须 < 2 MB、不支持通配符、非拉丁字符自动转 Punycode。
> 本仓库的 `domains.txt` 是面向 **AdGuard Home / Pi-hole 等外部工具或自行分片** 的完整下载产物，
> 条数远超单列表上限；若需直接作为一个 Cloudflare Gateway 列表上传，请改用 `MAX_ENTRIES=1000`（Standard）
> 或 `5000`（Enterprise），或按需自行拆分。
=======
> 数量可控（默认 12000 条），可直接作为 Cloudflare Gateway `DOMAIN` 列表使用。
> 本仓库**不做任何上传/同步**，只负责生成文件并提供随时可用的下载链接。
>>>>>>> 9d92522f4f1b1ca4aff04918edfddb9cd1447e79

---

## 📥 下载链接（始终指向最新版本）

把下面的 `OWNER/REPO` 换成你自己的仓库（如 `yourname/adblock-list`），`main` 换成你的默认分支：

| 文件 | raw.githubusercontent | jsDelivr CDN（国内更快） |
|---|---|---|
| **拦截列表** | `https://raw.githubusercontent.com/OWNER/REPO/main/lists/domains.txt` | `https://cdn.jsdelivr.net/gh/OWNER/REPO@main/lists/domains.txt` |
| **白名单** | `https://raw.githubusercontent.com/OWNER/REPO/main/lists/whitelist.txt` | `https://cdn.jsdelivr.net/gh/OWNER/REPO@main/lists/whitelist.txt` |
| CSV（带表头，供 Cloudflare 手动上传） | `.../lists/domains.csv` | `.../lists/domains.csv` |
| 构建统计 | `.../lists/stats.json` | `.../lists/stats.json` |

> Workflow 每次运行还会自动生成 `lists/LINKS.md`，里面是**你这个仓库的精确链接**，可直接复制。

### 链接说明
- **raw**：GitHub 原始文件，永远指向分支最新提交，URL 固定不变 → 可放心写进脚本/定时任务。
- **jsDelivr**：CDN 镜像，缓存通常几分钟到几小时；若需立刻拿到最新版本，在 URL 后加 `?t=<时间戳>` 或用 raw。

---

## 目录结构

```
.
<<<<<<< HEAD
├── .github/workflows/update.yml   # 定时（每天 UTC 01:00 / 北京时间 09:00）自动构建 + 生成下载链接 + 提交
=======
├── .github/workflows/update.yml   # 定时（每周一）自动构建 + 生成下载链接 + 提交
>>>>>>> 9d92522f4f1b1ca4aff04918edfddb9cd1447e79
├── config/
│   ├── sources.txt                # 广告/追踪/恶意域名 源 URL 列表
│   ├── whitelist.txt              # 白名单源（手工维护，支持 *.通配）
│   └── settings.env.example       # 参数说明（MAX_ENTRIES / MIN_SOURCES）
├── scripts/build_list.py          # 抓取+解析+频次排序+封顶 -> lists/（无第三方依赖）
└── lists/                         # 构建产物（自动生成/提交）
    ├── domains.txt                # 拦截列表（主产物）
    ├── whitelist.txt              # 白名单（主产物）
    ├── domains.csv                # 带表头，供 Cloudflare 手动上传
    ├── LINKS.md                   # 自动生成的精确下载链接
    └── stats.json                 # 构建统计
```

---

## 优选算法（"优选最常见的 ads"如何实现）

1. **抓取** `config/sources.txt` 里的每个源（自动识别 hosts / AdGuard ABP / 纯域名格式）。
<<<<<<< HEAD
2. **解析**为域名集合，并为每个源记录 `[权重] [地区]` 元数据（见下）。
3. 统计每个域名的四个维度：
   - `freq`：出现在多少个**不同源**（最常用）
   - `weighted`：这些源的**权重之和**（权重编码「更新频繁 / 权威度」，更新快、维护活跃的源权重更高）
   - `cn_hits`：命中多少个**中文专精源**（优先中文）
   - `is_new`：是否**本周期新出现**（对比上一版 `domains.txt`，优先最近更新）
4. **综合评分**：`score = weighted + CN_BONUS*cn_hits + NEW_BONUS*is_new`
5. **共识过滤**：仅保留出现在 `MIN_SOURCES`（默认 1 = 全量）个及以上源里的域名。
6. **排序**：score 降序 → freq 降序 → 域名升序（确定性）。
7. **封顶**：取 Top `MAX_ENTRIES`（默认 300000）写入 `domains.txt`。

> 四个优先级都编码进评分：**最常用**（freq / weighted）→ **更新频繁**（源权重）→ **最近更新**（is_new 加分）→ **优先中文**（CN_BONUS 加分）。

`config/sources.txt` 每行格式：`URL [权重] [地区]`，例如：

```
https://.../anti-AD.txt   3  cn      # 中文专精、高权重（更新频繁/权威）
https://.../oisd.txt      3  global  # 全球合并、高权重
https://.../some.txt      1  west    # 西方英文专精、默认权重
```

---

## 源构成（中文覆盖优先）

`config/sources.txt` 共 **32 个**源，按覆盖区域分为三类（详见文件内注释）：

| 分类 | 数量 | 说明 |
|---|---|---|
| 全球合并型 | 5 | 西方维护但聚合了全球（含中文）规则，如 StevenBlack / oisd / AdGuardSDNS / hagezi |
| 西方/英文专精 | 13 | 主要针对英语/西方站点与通用恶意/追踪，如 pgl.yoyo、Firebog 子集、anudeepND、Perflyst 等 |
| **中文专精** | **14** | 针对中国大陆/中文站点：Anti-AD、EasyList China、CJXList、yhosts、大圣净化、AWAvenue、乘风、AdRules、ADgk、ChinaList2.0、JieKouAD、1024_hosts 等 |

> **设计要点**：中文专精源（14）数量已超过「西方/英文专精」源（13），
> 再加上 Anti-AD（9.5 万行）、AdRules DNS（20 万行）等大体量中文聚合列表，
> 最终按"跨列表频次"优选时，中文域名会自然占据高频区，显著改善此前中文覆盖偏弱的问题。
> 若仍想进一步偏向中文，可在 `config/sources.txt` 中继续增删中文源，或调高 `MIN_SOURCES` 让高共识域名更靠前。
=======
2. **解析**为域名集合，统计每个域名在**多少个不同源**里出现 → 跨列表频次。
3. **共识过滤**：仅保留出现在 `MIN_SOURCES`（默认 2）个及以上源里的域名，过滤长尾噪声与误杀。
4. **排序**：频次降序 → 字典序（确定性 tie-break）。
5. **封顶**：取 Top `MAX_ENTRIES`（默认 12000）写入 `domains.txt`。

结果 = 全网最常见、被最多广告列表共同确认的域名，单个文件、数量可控。
>>>>>>> 9d92522f4f1b1ca4aff04918edfddb9cd1447e79

---

## 白名单机制

`config/whitelist.txt` 是你手工维护的白名单源，支持两种写法：

```
example.com        # 精确放行
*.example.com      # 放行该域名及其所有子域
```

**生成时**：命中白名单的域名不会进入拦截列表。
**生成后**：`lists/whitelist.txt` 是最终产物，全部为**精确域名**（含 apex 与源列表中实际出现过的子域）——
因为 Cloudflare Gateway `DOMAIN` 列表**不支持 `*.` 通配符**，这样展开才能直接上传使用。

内置保守默认值：人机验证（Cloudflare / hCaptcha）、支付（Stripe / PayPal）、常用 CDN、
基础服务（Google APIs / Apple / Microsoft）、视频播放与错误监控（Sentry）等，按需增删。

---

## 用法

### 1. Fork 本仓库
把以上文件放进你自己的仓库，**默认分支名**记下来（用于拼下载链接）。

### 2. 触发构建
<<<<<<< HEAD
- 自动：每天（UTC 01:00，北京时间 09:00）。
=======
- 自动：每周一 06:00 UTC。
>>>>>>> 9d92522f4f1b1ca4aff04918edfddb9cd1447e79
- 手动：Actions → *Update Ad Blocklist* → *Run workflow*。

### 3. 拿到文件
用上面的下载链接，或直接取仓库里的 `lists/domains.txt` / `lists/whitelist.txt`。

### 4. 用到 Cloudflare Gateway（手动，两步）
<<<<<<< HEAD
> ⚠️ 重要：官方文档规定 **单个 Gateway 列表上限 Standard 1000 / Enterprise 5000 条，CSV 须 < 2 MB**，
> 不支持通配符，非拉丁域名自动转 Punycode。本仓库默认的 30 万条 `domains.txt` **无法直接作为一个 Cloudflare 列表上传**，
> 必须二选一：① 把 `MAX_ENTRIES` 设为 `1000`（Standard）或 `5000`（Enterprise）后重新构建；② 自行将列表拆分到多个列表。

1. 若按 Cloudflare 上限构建，Zero Trust → **Reusable components → Lists → Upload CSV**，上传 `lists/domains.csv`（类型选 **DOMAIN**）；
=======
1. Zero Trust → **Reusable components → Lists → Upload CSV**，上传 `lists/domains.csv`（类型选 **DOMAIN**）；
>>>>>>> 9d92522f4f1b1ca4aff04918edfddb9cd1447e79
   再上传 `lists/whitelist.txt`（类型 **DOMAIN**，需自行补 `value` 表头或直接粘贴条目）。
2. **Gateway → DNS policies** 建两条策略：

   | 策略 | Selector / Operator | Action | Precedence |
   |---|---|---|---|
   | 放行白名单 | `Domain` `in list` = 白名单列表 | **Allow** | **100**（更小 = 优先） |
   | 拦截广告 | `Domain` `in list` = 拦截列表 | **Block** | 200 |

   > Allow 的 precedence 必须小于 Block，白名单才会优先生效。
<<<<<<< HEAD
   > 若上传被拒，按计划调低：Standard 1000 / Enterprise 5000。
=======
   > 默认封顶 12000 条（实测 Gateway DOMAIN 列表可接受）。若上传被拒，可调低：Standard 1000 / Enterprise 5000。
>>>>>>> 9d92522f4f1b1ca4aff04918edfddb9cd1447e79

### 5. 本地运行

```bash
python scripts/build_list.py
# 可选参数：
<<<<<<< HEAD
#   --max-entries 300000  --min-sources 1
#   --cn-bonus 2.0  --new-bonus 1.0
=======
#   --max-entries 12000  --min-sources 2
>>>>>>> 9d92522f4f1b1ca4aff04918edfddb9cd1447e79
#   --sources config/sources.txt  --whitelist config/whitelist.txt  --out-dir lists
```

---

## 调参建议

| 目标 | 设置 |
|---|---|
<<<<<<< HEAD
| 更纯净、极少误杀 | `MIN_SOURCES=3`（需被 ≥3 个源共同确认） |
| 更偏中文 | 调高 `CN_BONUS`（如 `4.0`）或只保留 `region=cn` 的源 |
| 更偏最近更新 | 调高 `NEW_BONUS`（如 `2.0`） |
| 默认完整下载文件 | `MAX_ENTRIES=300000`（即 1000×300） |
| 直接上传到 Cloudflare Gateway（单列表） | `MAX_ENTRIES=1000`（Standard）或 `5000`（Enterprise） |
| 遇到误杀 | 把域名（或 `*.域名`）加入 `config/whitelist.txt` |

> `MAX_ENTRIES=300000` 是面向 AdGuard Home / Pi-hole 等外部工具或自行分片的**完整下载文件**上限，
> 已超过 Cloudflare Gateway 单列表上限（Standard 1000 / Enterprise 5000）。若直接上传到 Gateway，请按上表调低。
=======
| 更纯净、极少误杀 | `MIN_SOURCES=3`，`MAX_ENTRIES=12000` |
| 覆盖更广 | `MAX_ENTRIES=50000`（或更高） |
| 遇到误杀 | 把域名（或 `*.域名`）加入 `config/whitelist.txt` |

> 若只在本仓库外消费列表（如 AdGuard / Pi-hole），`MAX_ENTRIES` 可以自由调大；
> 若上传到 Cloudflare Gateway 被拒，按计划调低：Standard 1000 / Enterprise 5000；默认 12000 已实测可接受。
>>>>>>> 9d92522f4f1b1ca4aff04918edfddb9cd1447e79

---

## 许可
代码以 MIT 许可发布；各源列表版权归其各自维护者所有，请遵守其许可与使用条款。
