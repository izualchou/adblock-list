#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_list.py — 抓取、合并并*加权优选*广告/追踪域名，输出两个可直接下载的列表文件。

优选算法（兼顾「控制数量」与「优先中文 / 更新频繁 / 最近更新 / 最常用」）：
  1. 下载每个源（hosts / AdGuard / domain 格式，自动识别）。
  2. 每个源可带 [权重] [地区] 元数据（见 config/sources.txt）：
       - 权重   ：越大 = 越权威 / 更新越频繁 / 维护越活跃（编码「更新频繁」）
       - 地区   ：cn=中文专精 / west=西方英文 / global=全球（编码「优先中文」）
  3. 统计每个域名的：
       - freq       ：出现在多少个不同源（「最常用」）
       - weighted   ：这些源的权重之和
       - cn_hits    ：命中多少个中文专精源
       - is_new     ：是否本周期新出现（对比上一版 domains.txt，「最近更新」）
  4. 综合评分：score = weighted + CN_BONUS*cn_hits + NEW_BONUS*is_new
  5. 只保留出现在 >= MIN_SOURCES 个源里的域名（共识过滤，默认 1 = 全量）。
  6. 按 score 降序、freq 降序、字典序排序，封顶 MAX_ENTRIES -> domains.txt。

输出（全部写入 lists/）：
  lists/domains.txt   — 拦截列表：每行一个精确域名（主产物）
  lists/domains.csv   — 同上，带表头 value,description
  lists/whitelist.txt — 白名单：永不拦截的精确域名（由 config/whitelist.txt 生成）
  lists/stats.json    — 构建统计与评分明细

说明：Gateway DOMAIN 列表不支持 *. 通配符，因此白名单里的 `*.example.com`
会展开为「该 apex 域名 + 源列表中实际出现过的所有子域名」，全部为精确域名。
"""

import os
import re
import sys
import json
import argparse
import datetime
import ipaddress
import time
import urllib.request
import urllib.error

# --------------------------------------------------------------------------- #
# 配置（命令行 > 环境变量 > 默认值）
# --------------------------------------------------------------------------- #
_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SOURCES = os.path.join(_HERE, "..", "config", "sources.txt")
DEFAULT_WHITELIST = os.path.join(_HERE, "..", "config", "whitelist.txt")
DEFAULT_OUT_DIR = os.path.join(_HERE, "..", "lists")

MAX_ENTRIES = int(os.environ.get("MAX_ENTRIES", "300000"))    # 拦截列表封顶（下载产物条数上限）
MIN_SOURCES = int(os.environ.get("MIN_SOURCES", "1"))         # 至少出现在几个源里（默认 1 = 全量）
TIMEOUT = int(os.environ.get("FETCH_TIMEOUT", "90"))          # 单源下载超时（秒）
MAX_RETRIES = int(os.environ.get("FETCH_RETRIES", "3"))       # 单源失败重试次数
RETRY_BACKOFF = int(os.environ.get("FETCH_BACKOFF", "5"))     # 重试退避（秒）
CN_BONUS = float(os.environ.get("CN_BONUS", "2.0"))          # 每命中一个中文源，评分额外加分
NEW_BONUS = float(os.environ.get("NEW_BONUS", "1.0"))         # 本周期新增域名，评分额外加分

# 合法域名：标签 + 2~63 字母的 TLD（不处理 IDN，Gateway 会自动转 Punycode）
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)
IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
IPV6_SPECIAL = {"::", "::1", "0.0.0.0", "127.0.0.1"}


# --------------------------------------------------------------------------- #
# 域名解析
# --------------------------------------------------------------------------- #
def is_ip(token: str) -> bool:
    if token in IPV6_SPECIAL:
        return True
    if IPV4_RE.match(token):
        try:
            ipaddress.ip_address(token)
            return True
        except ValueError:
            return False
    if ":" in token:  # 粗略判断 IPv6
        return True
    return False


def normalize_domain(s: str):
    """合法域名转小写返回，否则返回 None。"""
    s = s.strip().lower()
    if not s or s in ("localhost",):
        return None
    if is_ip(s):
        return None
    if DOMAIN_RE.match(s):
        return s
    return None


def parse_abp(token: str):
    """从 AdGuard / uBlock (ABP) 规则中提取域名。"""
    t = token.strip()
    if t.startswith("@@"):          # 例外规则，跳过
        return None
    if "badfilter" in t:            # 反过滤规则，跳过
        return None
    if t.startswith("||"):
        t = t[2:]
    t = t.lstrip("|")
    # 在遇到 ABP 分隔符处截断
    for sep in ("^", "$", "|", "/", "*", "?", "#", ",", ":", " "):
        idx = t.find(sep)
        if idx != -1:
            t = t[:idx]
    if not t:
        return None
    return t.split("#")[0].strip()


def parse_line(line: str):
    """解析单行（hosts / ABP / 纯域名），返回域名或 None。"""
    line = line.rstrip("\n")
    stripped = line.strip()
    if not stripped:
        return None
    if stripped[0] in "#!;":
        return None
    if stripped.startswith("@@"):
        return None
    if "##" in stripped:            # 元素隐藏规则（CSS），跳过
        return None
    if stripped.startswith("["):   # [Adblock Plus 2.0] 等头部，跳过
        return None
    if "badfilter" in stripped:
        return None

    parts = stripped.split()
    first = parts[0]
    # hosts 风格：首列为 IP
    if is_ip(first) or first.lower() == "localhost":
        if len(parts) < 2:
            return None
        candidate = parts[1]
    else:
        candidate = parse_abp(first)
        if candidate is None:
            return None

    candidate = candidate.split("#")[0].strip()
    return normalize_domain(candidate)


# --------------------------------------------------------------------------- #
# 读取源（支持 URL [权重] [地区]）
# --------------------------------------------------------------------------- #
def fetch_source(url: str) -> str:
    """读取源内容：本地路径 / file:// 直接读；否则 HTTP 下载。"""
    if url.startswith("file://"):
        path = url[7:]
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    # 本地文件：绝对路径、以 ./ ../ 开头，或当前工作目录下确实存在该文件
    if url.startswith("/") or url.startswith("./") or url.startswith("../") or os.path.exists(url):
        with open(url, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cf-gateway-adblock-builder/1.0"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset, errors="replace")
        except Exception as e:  # 网络抖动/超时，重试
            last_err = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF)
                continue
    raise last_err


def load_source_list(path: str):
    """逐行解析 sources.txt，返回 [(url, weight, region), ...]。

    每行格式：URL [权重] [地区]，# 开头或空行跳过。
    权重默认 1.0；地区默认 'global'，仅 'cn'/'west'/'global' 有效。
    """
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            tokens = line.split()
            url = tokens[0]
            weight = 1.0
            region = "global"
            if len(tokens) >= 2:
                try:
                    weight = float(tokens[1])
                except ValueError:
                    weight = 1.0
            if len(tokens) >= 3 and tokens[2].lower() in ("cn", "west", "global"):
                region = tokens[2].lower()
            out.append((url, weight, region))
    return out


# --------------------------------------------------------------------------- #
# 上一版域名（用于「最近更新」新增检测）
# --------------------------------------------------------------------------- #
def load_previous_domains(out_dir: str):
    """读取上一版 domains.txt（若存在），返回 set；不存在则返回空集合。"""
    prev = os.path.join(out_dir, "domains.txt")
    if not os.path.exists(prev):
        return set()
    with open(prev, "r", encoding="utf-8") as fh:
        return {line.strip().lower() for line in fh if line.strip()}


# --------------------------------------------------------------------------- #
# 白名单
# --------------------------------------------------------------------------- #
def load_whitelist(path: str):
    """读取 config/whitelist.txt，返回 (exact_set, wildcard_apexes)。"""
    exact, wild = set(), []
    if not os.path.exists(path):
        return exact, wild
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            d = raw.strip().lower()
            if not d or d.startswith("#"):
                continue
            if d.startswith("*."):
                apex = normalize_domain(d[2:])
                if apex:
                    wild.append(apex)
            else:
                dom = normalize_domain(d)
                if dom:
                    exact.add(dom)
    return exact, wild


def matches_wildcard(domain: str, wild: list):
    """返回命中的 apex，未命中返回 None。"""
    for apex in wild:
        if domain == apex or domain.endswith("." + apex):
            return apex
    return None


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def build(sources_path, whitelist_path, out_dir, max_entries, min_sources,
          cn_bonus=CN_BONUS, new_bonus=NEW_BONUS):
    os.makedirs(out_dir, exist_ok=True)
    wl_exact, wl_wild = load_whitelist(whitelist_path)
    prev_domains = load_previous_domains(out_dir)

    # domain -> {sources: set(idx), weighted: float, cn_hits: int}
    data = {}
    source_stats = []
    total_raw = 0
    wild_matched = set()      # 被通配白名单命中的实际域名（用于展开白名单）
    sources = load_source_list(sources_path)

    for idx, (url, weight, region) in enumerate(sources):
        try:
            content = fetch_source(url)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
            source_stats.append({"url": url, "ok": False, "domains": 0, "error": str(e)})
            print(f"[WARN] 源下载失败: {url} -> {e}", file=sys.stderr)
            continue

        seen = set()
        for line in content.splitlines():
            dom = parse_line(line)
            if dom is None:
                continue
            total_raw += 1
            # 白名单优先：精确命中
            if dom in wl_exact:
                continue
            # 通配命中：记录后跳过，并加入白名单展开集合
            if matches_wildcard(dom, wl_wild):
                wild_matched.add(dom)
                continue
            seen.add(dom)
            rec = data.get(dom)
            if rec is None:
                rec = {"sources": set(), "weighted": 0.0, "cn_hits": 0}
                data[dom] = rec
            rec["sources"].add(idx)
            rec["weighted"] += weight
            if region == "cn":
                rec["cn_hits"] += 1

        source_stats.append({"url": url, "ok": True, "domains": len(seen),
                             "weight": weight, "region": region})

    # ---- 评分 + 共识过滤 + 排序 + 封顶 ----
    ranked = []
    for dom, rec in data.items():
        freq = len(rec["sources"])
        if freq < min_sources:
            continue
        is_new = 1 if dom not in prev_domains else 0
        score = rec["weighted"] + cn_bonus * rec["cn_hits"] + new_bonus * is_new
        ranked.append((dom, freq, rec["weighted"], rec["cn_hits"], is_new, score))

    # 排序：score 降序 > freq 降序 > 域名升序（确定性）
    ranked.sort(key=lambda r: (-r[5], -r[1], r[0]))
    final = ranked[:max_entries]
    final_domains = [r[0] for r in final]
    final_cn = sum(1 for r in final if r[3] > 0)
    final_new = sum(1 for r in final if r[4] > 0)

    txt_path = os.path.join(out_dir, "domains.txt")
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(final_domains) + ("\n" if final_domains else ""))

    csv_path = os.path.join(out_dir, "domains.csv")
    with open(csv_path, "w", encoding="utf-8") as fh:
        fh.write("value,description\n")
        for dom, freq, weighted, cn_hits, is_new, score in final:
            tag = "cn" if cn_hits > 0 else "intl"
            newtag = " new" if is_new else ""
            fh.write(f'{dom},"ad/tracker - {freq} sources [{tag}]{newtag}"\n')

    # ---- 白名单列表：精确域名 + apex + 实际命中的子域 ----
    whitelist_domains = set(wl_exact) | set(wl_wild) | wild_matched
    whitelist_sorted = sorted(whitelist_domains)
    wl_path = os.path.join(out_dir, "whitelist.txt")
    with open(wl_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(whitelist_sorted) + ("\n" if whitelist_sorted else ""))

    # ---- 统计 ----
    stats = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scoring": {
            "min_sources": min_sources,
            "max_entries": max_entries,
            "cn_bonus": cn_bonus,
            "new_bonus": new_bonus,
            "formula": "score = weighted_sum + cn_bonus*cn_hits + new_bonus*is_new",
        },
        "sources_total": len(sources),
        "sources_ok": sum(1 for s in source_stats if s["ok"]),
        "total_raw_lines": total_raw,
        "unique_domains_after_parse": len(data),
        "after_consensus_filter": len(ranked),
        "blocklist_count": len(final_domains),
        "blocklist_cn_domains": final_cn,
        "blocklist_new_domains": final_new,
        "whitelist_count": len(whitelist_sorted),
        "top_20": [
            {"domain": d, "freq": f, "weighted": w, "cn_hits": c, "is_new": n, "score": s}
            for d, f, w, c, n, s in final[:20]
        ],
        "sources": source_stats,
    }
    with open(os.path.join(out_dir, "stats.json"), "w", encoding="utf-8") as fh:
        json.dump(stats, fh, indent=2, ensure_ascii=False)

    print(f"[OK] 解析 {len(data)} 个去重域名；共识(min>={min_sources})后 {len(ranked)} 个；"
          f"拦截列表写入 {len(final_domains)} 个（含中文 {final_cn}、新增 {final_new}）-> {txt_path}")
    print(f"[OK] 白名单写入 {len(whitelist_sorted)} 个 -> {wl_path}")
    return stats


def main():
    ap = argparse.ArgumentParser(description="Build a curated ad-block domain list + whitelist.")
    ap.add_argument("--sources", default=DEFAULT_SOURCES)
    ap.add_argument("--whitelist", default=DEFAULT_WHITELIST)
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--max-entries", type=int, default=MAX_ENTRIES)
    ap.add_argument("--min-sources", type=int, default=MIN_SOURCES)
    ap.add_argument("--cn-bonus", type=float, default=CN_BONUS)
    ap.add_argument("--new-bonus", type=float, default=NEW_BONUS)
    args = ap.parse_args()
    build(args.sources, args.whitelist, args.out_dir, args.max_entries, args.min_sources,
          cn_bonus=args.cn_bonus, new_bonus=args.new_bonus)


if __name__ == "__main__":
    main()
