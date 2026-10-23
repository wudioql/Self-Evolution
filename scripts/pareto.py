# -*- coding: utf-8 -*-
"""报警帕累托报告生成器（零依赖，Python 3.11+ 标准库）。

用途
    把一份本地交接 / 报警记录（Markdown 表格）按配置归类，生成单文件离线 HTML：
    帕累托图、分类明细、月度分布、类别内处置指向、Top N 根因、归类口径、复现说明。

用法
    python scripts/pareto.py --config data/pareto/<配置>.json
    python scripts/pareto.py --config data/pareto/<配置>.json --check   # 只校验，不写文件

目录约定（一次分析 = 一个文件夹）
    data/pareto/
      <配置>.json             类别、行号归属、关键词、Top 3 文案
      report-template.html    页面模板（占位符 __PARETO_DATA_JSON__ / __TITLE_META__）
      <输出>.html             生成结果（可公开，不含原始记录文本）

配置关键字段
    input      原始 Markdown 表格路径，相对配置文件
    output     输出 HTML，相对配置文件
    template   模板路径，相对配置文件
    columns    表头列顺序（与表格列数一致）
    categories [{code,name,short,rule,rows[],excluded?}]
               rows 是表内序号（# 列）；excluded=true 的类别从报警口径剔除
    facets     {category, note, items:[{label,keywords[]}]} 类别内多标签统计
    top3       [{title,root,evidence,verify,expect}]
    otherNotes / caveats  说明文字

校验
    行号必须全覆盖且不重复；同一行不能进两个类别；表格列数与 columns 一致。
    任一不满足即报错退出，不生成半成品。
"""

import argparse
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    for key in ("input", "output", "template", "columns", "categories"):
        if key not in cfg:
            raise SystemExit(f"配置缺少字段：{key}")
    return cfg


def parse_table(path, columns):
    """解析 Markdown 表格：表头行之后、| 分隔的每一行，首列必须是序号。"""
    ncol = len(columns)
    rows = []
    header_seen = False
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not header_seen:
                if len(cells) == ncol and "日期" in cells:
                    header_seen = True
                continue
            if len(cells) != ncol:
                raise SystemExit(f"列数不符（期望 {ncol}，实际 {len(cells)}）：{line[:40]}")
            if set(line) <= set("|-: "):
                continue
            if not re.fullmatch(r"\d+", cells[0]):
                continue
            item = dict(zip(columns, cells))
            item["n"] = int(item["n"])
            rows.append(item)
    if not rows:
        raise SystemExit("未解析到数据行，请检查表格表头是否含「日期」且列数与 columns 一致")
    return rows


def assign_rows(rows, categories):
    by_n = {r["n"]: r for r in rows}
    assigned = {}
    for cat in categories:
        for n in cat["rows"]:
            if n not in by_n:
                raise SystemExit(f"类别 {cat['code']} 引用了不存在的行号：{n}")
            if n in assigned:
                raise SystemExit(f"行号 {n} 同时属于 {assigned[n]} 与 {cat['code']}")
            assigned[n] = cat["code"]
    missing = sorted(set(by_n) - set(assigned))
    if missing:
        raise SystemExit(f"有记录未归类：{missing}")
    return by_n, assigned


def month_range(months):
    """补齐中间缺失月份（含首尾）。"""
    nums = []
    for m in months:
        y, mm = m.split("-")
        nums.append(int(y) * 12 + int(mm))
    start, end = min(nums), max(nums)
    out = []
    for v in range(start, end + 1):
        out.append(f"{v // 12:04d}-{v % 12:02d}")
    return out


def dedupe_events(rows, min_chars, max_gap):
    """描述互相包含且间隔在 max_gap 天内 → 视为同一事件的跨班重复交接。"""
    parent = {r["n"]: r["n"] for r in rows}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, a in enumerate(rows):
        da = re.sub(r"\s+", "", a["desc"])
        for b in rows[i + 1:]:
            db = re.sub(r"\s+", "", b["desc"])
            short, long_ = (da, db) if len(da) <= len(db) else (db, da)
            if len(short) < min_chars or short not in long_:
                continue
            try:
                gap = abs((date.fromisoformat(a["date"]) - date.fromisoformat(b["date"])).days)
            except ValueError:
                continue
            if gap <= max_gap:
                union(a["n"], b["n"])
    groups = {}
    for r in rows:
        groups.setdefault(find(r["n"]), []).append(r["n"])
    return groups


def build(cfg, rows):
    by_n, assigned = assign_rows(rows, cfg["categories"])
    excluded = [c for c in cfg["categories"] if c.get("excluded")]
    alarm_rows = [r for r in rows if assigned[r["n"]] not in {c["code"] for c in excluded}]
    alarms = len(alarm_rows)

    stats = OrderedDict()
    for cat in cfg["categories"]:
        sel = [by_n[n] for n in cat["rows"]]
        stats[cat["code"]] = {
            "code": cat["code"],
            "name": cat["name"],
            "short": cat.get("short", cat["name"]),
            "count": len(sel),
            "down": sum(1 for r in sel if r.get("status") == "DOWN"),
            "monpa": sum(1 for r in sel if r.get("monpa") == cfg.get("monpaMark", "✔")),
            "excluded": bool(cat.get("excluded")),
        }

    live = [s for s in stats.values() if not s["excluded"]]
    live.sort(key=lambda s: (-s["count"], s["code"]))
    cum = 0.0
    for s in live:
        s["pct"] = round(s["count"] / alarms * 100, 1)
        cum += s["count"] / alarms * 100
        s["cum"] = round(cum, 1)
    if live:
        live[-1]["cum"] = 100.0

    # 月度（报警口径）
    months = {}
    for r in alarm_rows:
        months[r["date"][:7]] = months.get(r["date"][:7], 0) + 1
    full_months = month_range(sorted(months))
    month_list = [[m, months.get(m, 0)] for m in full_months]
    zero_months = [m for m, c in month_list if c == 0]
    peak = max(month_list, key=lambda d: d[1])[0] if month_list else ""
    months_note = "报警类记录按月计数"
    if zero_months:
        months_note += "（" + "、".join(zero_months) + " 无记录）"

    # 类别内处置指向（多标签）
    facet_cfg = cfg.get("facets")
    facets = {"note": "", "total": 0, "items": []}
    if facet_cfg:
        code = facet_cfg["category"]
        scope = [r for r in rows if assigned[r["n"]] == code]
        facets["note"] = facet_cfg.get("note", "")
        facets["total"] = len(scope)
        for item in facet_cfg["items"]:
            hits = 0
            for r in scope:
                text = (r.get("desc", "") + " " + r.get("action", "")).lower()
                if any(k.lower() in text for k in item["keywords"]):
                    hits += 1
            facets["items"].append({"label": item["label"], "count": hits})

    # 事件归并
    dd = cfg.get("dedupe", {})
    groups = dedupe_events(rows, int(dd.get("minChars", 20)), int(dd.get("maxDayGap", 7)))
    events = len(groups)
    multi = sum(1 for v in groups.values() if len(v) > 1)
    extra_caveat = (
        f"按描述重复归并（较短描述 ≥{dd.get('minChars', 20)} 字、间隔 ≤{dd.get('maxDayGap', 7)} 天）"
        f"后约 {events} 起；记录 {len(rows)} 条，跨班重复 {len(rows) - events} 条（{multi} 组多记录）。"
    )

    data = {
        "title": cfg["title"],
        "eyebrow": cfg.get("eyebrow", "Pareto Analysis"),
        "period": cfg["period"],
        "generatedOn": cfg.get("generatedOn", ""),
        "kpis": {
            "records": len(rows),
            "alarms": alarms,
            "excluded": len(rows) - alarms,
            "top1Pct": live[0]["pct"] if live else 0,
            "top1Count": live[0]["count"] if live else 0,
            "top3Cum": live[min(2, len(live) - 1)]["cum"] if live else 0,
        },
        "pareto": [{k: v for k, v in s.items() if k != "excluded"} for s in live],
        "months": month_list,
        "monthsPeak": peak,
        "monthsNote": months_note,
        "facets": facets,
        "top3": cfg.get("top3", []),
        "rules": [{"name": c["name"], "rule": c.get("rule", "")} for c in cfg["categories"]],
        "otherNotes": cfg.get("otherNotes", []),
        "caveats": list(cfg.get("caveats", [])) + [extra_caveat],
    }
    return data


def repro_info(cfg, config_path):
    cfg_dir = os.path.dirname(os.path.abspath(config_path))

    def rel(p):
        return os.path.relpath(os.path.abspath(os.path.join(cfg_dir, p)), ROOT).replace("\\", "/")

    return {
        "command": "python scripts/pareto.py --config " + rel(os.path.basename(config_path)),
        "input": rel(cfg["input"]),
        "config": rel(os.path.basename(config_path)),
        "template": rel(cfg["template"]),
        "files": [rel(cfg["output"])],
    }


def render(cfg, data, config_path):
    cfg_dir = os.path.dirname(os.path.abspath(config_path))
    template_path = os.path.join(cfg_dir, cfg["template"])
    with open(template_path, encoding="utf-8") as f:
        html = f.read()
    data["repro"] = repro_info(cfg, config_path)
    payload = "window.PARETO_DATA = " + json.dumps(data, ensure_ascii=False, indent=2) + ";"
    if "__PARETO_DATA_JSON__" not in html:
        raise SystemExit("模板缺少占位符 __PARETO_DATA_JSON__")
    html = html.replace("__PARETO_DATA_JSON__", payload)
    html = html.replace("__TITLE_META__", cfg.get("period", ""))
    return html


def main(argv=None):
    ap = argparse.ArgumentParser(description="报警帕累托报告生成器")
    ap.add_argument("--config", required=True, help="配置文件路径（.json）")
    ap.add_argument("--input", help="覆盖配置里的原始表路径")
    ap.add_argument("--output", help="覆盖配置里的输出路径")
    ap.add_argument("--check", action="store_true", help="只校验数据与配置，不写文件")
    args = ap.parse_args(argv)

    config_path = os.path.abspath(args.config)
    cfg = load_config(config_path)
    cfg_dir = os.path.dirname(config_path)

    input_path = args.input or os.path.join(cfg_dir, cfg["input"])
    rows = parse_table(input_path, cfg["columns"])
    data = build(cfg, rows)

    if args.check:
        print(f"校验通过：{len(rows)} 条记录，报警类 {data['kpis']['alarms']} 条，类别 {len(cfg['categories'])} 个")
        return 0

    output_path = args.output or os.path.join(cfg_dir, cfg["output"])
    html = render(cfg, data, config_path)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"已生成：{os.path.relpath(output_path, ROOT)}")
    print(f"记录 {len(rows)} 条 · 报警类 {data['kpis']['alarms']} 条 · "
          f"Top1 {data['kpis']['top1Pct']}% · Top3 累计 {data['kpis']['top3Cum']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
