# 广告拦截域名列表（自动构建 · 含白名单）

一个跑在 GitHub 上的自动化方案：**抓取 → 合并 → 按"跨列表出现频次"优选 → 数量封顶**，
产出两个文件并持续保持最新：

- **`lists/domains.txt`** — 拦截列表（单行一个精确域名）
- **`lists/whitelist.txt`** — 白名单（永不拦截的域名）

> 核心思想：不追求"域名越多越好"，而是**只保留被多个权威源共同确认的、最常见的广告/追踪域名**，
> 数量可控（默认 12000 条），可直接作为 Cloudflare Gateway `DOMAIN` 列表使用。
> 本仓库**不做任何上传/同步**，只负责生成文件并提供随时可用的下载链接。

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
├── .github/workflows/update.yml   # 定时（每周一）自动构建 + 生成下载链接 + 提交
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
2. **解析**为域名集合，统计每个域名在**多少个不同源**里出现 → 跨列表频次。
3. **共识过滤**：仅保留出现在 `MIN_SOURCES`（默认 2）个及以上源里的域名，过滤长尾噪声与误杀。
4. **排序**：频次降序 → 字典序（确定性 tie-break）。
5. **封顶**：取 Top `MAX_ENTRIES`（默认 12000）写入 `domains.txt`。

结果 = 全网最常见、被最多广告列表共同确认的域名，单个文件、数量可控。

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
- 自动：每周一 06:00 UTC。
- 手动：Actions → *Update Ad Blocklist* → *Run workflow*。

### 3. 拿到文件
用上面的下载链接，或直接取仓库里的 `lists/domains.txt` / `lists/whitelist.txt`。

### 4. 用到 Cloudflare Gateway（手动，两步）
1. Zero Trust → **Reusable components → Lists → Upload CSV**，上传 `lists/domains.csv`（类型选 **DOMAIN**）；
   再上传 `lists/whitelist.txt`（类型 **DOMAIN**，需自行补 `value` 表头或直接粘贴条目）。
2. **Gateway → DNS policies** 建两条策略：

   | 策略 | Selector / Operator | Action | Precedence |
   |---|---|---|---|
   | 放行白名单 | `Domain` `in list` = 白名单列表 | **Allow** | **100**（更小 = 优先） |
   | 拦截广告 | `Domain` `in list` = 拦截列表 | **Block** | 200 |

   > Allow 的 precedence 必须小于 Block，白名单才会优先生效。
   > 默认封顶 12000 条（实测 Gateway DOMAIN 列表可接受）。若上传被拒，可调低：Standard 1000 / Enterprise 5000。

### 5. 本地运行

```bash
python scripts/build_list.py
# 可选参数：
#   --max-entries 12000  --min-sources 2
#   --sources config/sources.txt  --whitelist config/whitelist.txt  --out-dir lists
```

---

## 调参建议

| 目标 | 设置 |
|---|---|
| 更纯净、极少误杀 | `MIN_SOURCES=3`，`MAX_ENTRIES=12000` |
| 覆盖更广 | `MAX_ENTRIES=50000`（或更高） |
| 遇到误杀 | 把域名（或 `*.域名`）加入 `config/whitelist.txt` |

> 若只在本仓库外消费列表（如 AdGuard / Pi-hole），`MAX_ENTRIES` 可以自由调大；
> 若上传到 Cloudflare Gateway 被拒，按计划调低：Standard 1000 / Enterprise 5000；默认 12000 已实测可接受。

---

## 许可
代码以 MIT 许可发布；各源列表版权归其各自维护者所有，请遵守其许可与使用条款。
