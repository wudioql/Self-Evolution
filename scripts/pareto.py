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
        nums.append(int(y) * 12 + int(mm) - 1)
    start, end = min(nums), max(nums)
    out = []
    for v in range(start, end + 1):
        out.append(f"{v // 12:04d}-{v % 12 + 1:02d}")
    return out


def merge_events(rows, categories, groups_cfg, monpa_mark):
    """按配置的 eventGroups 把同一事件的跨班记录合并成一条事件记录。

    规则由人工确认后写进配置，本函数只负责合并与校验：
    组内默认必须同类；确属同一事件但主诉类别不同时，可用组的 `cat` 字段
    指定归入哪一类（如颗粒 NG 由密封圈泄漏引发）。行号必须存在、不与其他组重叠；
    合并后 DOWN / MON PA 取组内任一。
    """
    by_n = {r["n"]: r for r in rows}
    cat_of = {n: c["code"] for c in categories for n in c["rows"]}
    valid_cats = {c["code"] for c in categories}
    group_of = {}
    for gi, g in enumerate(groups_cfg):
        cats = set()
        for n in g["rows"]:
            if n not in by_n:
                raise SystemExit(f"eventGroups 引用了不存在的行号：{n}")
            if n in group_of:
                raise SystemExit(f"行号 {n} 出现在多个 eventGroups")
            group_of[n] = gi
            cats.add(cat_of[n])
        if len(cats) > 1 and not g.get("cat"):
            raise SystemExit(f"eventGroup {g['rows']} 跨类别且未指定 cat：{sorted(cats)}")
        if g.get("cat") and g["cat"] not in valid_cats:
            raise SystemExit(f"eventGroup {g['rows']} 的 cat 不存在：{g['cat']}")

    event_rows = []
    seen = set()
    for r in rows:
        gi = group_of.get(r["n"])
        if gi is None:
            event_rows.append({"n": r["n"], "cat": cat_of[r["n"]], "date": r["date"],
                               "status": r["status"], "monpa": r["monpa"] == monpa_mark})
            continue
        if gi in seen:
            continue
        seen.add(gi)
        members = [by_n[n] for n in groups_cfg[gi]["rows"]]
        first = groups_cfg[gi]["rows"][0]
        event_rows.append({
            "n": first,
            "cat": groups_cfg[gi].get("cat") or cat_of[first],
            "date": min(m["date"] for m in members),
            "status": "DOWN" if any(m["status"] == "DOWN" for m in members) else members[0]["status"],
            "monpa": any(m["monpa"] == monpa_mark for m in members),
        })
    return event_rows


def live_list(event_rows, categories, alarms_total):
    """非排除类别按计数降序，返回带占比与累计的帕累托序列。"""
    stats = []
    for cat in categories:
        if cat.get("excluded"):
            continue
        sel = [e for e in event_rows if e["cat"] == cat["code"]]
        stats.append({
            "code": cat["code"],
            "name": cat["name"],
            "short": cat.get("short", cat["name"]),
            "count": len(sel),
            "down": sum(1 for e in sel if e["status"] == "DOWN"),
            "monpa": sum(1 for e in sel if e["monpa"]),
        })
    stats.sort(key=lambda s: (-s["count"], s["code"]))
    cum = 0.0
    for s in stats:
        s["pct"] = round(s["count"] / alarms_total * 100, 1) if alarms_total else 0.0
        cum += s["count"] / alarms_total * 100 if alarms_total else 0.0
        s["cum"] = round(cum, 1)
    if stats:
        stats[-1]["cum"] = 100.0
    return stats


def build(cfg, rows):
    by_n, assigned = assign_rows(rows, cfg["categories"])
    excluded = [c for c in cfg["categories"] if c.get("excluded")]
    alarm_rows = [r for r in rows if assigned[r["n"]] not in {c["code"] for c in excluded}]
    alarms = len(alarm_rows)
    monpa_mark = cfg.get("monpaMark", "✔")

    # 记录级
    record_rows = [{"n": r["n"], "cat": assigned[r["n"]], "date": r["date"],
                    "status": r["status"], "monpa": r["monpa"] == monpa_mark} for r in rows]
    record_live = live_list(record_rows, cfg["categories"], alarms)

    # 事件级（人工确认的 eventGroups）
    event_groups = cfg.get("eventGroups", [])
    pending_groups = cfg.get("pendingGroups", [])
    event_rows = merge_events(rows, cfg["categories"], event_groups, monpa_mark)
    excluded_codes = {c["code"] for c in excluded}
    alarm_event_rows = [e for e in event_rows if e["cat"] not in excluded_codes]
    alarm_events = len(alarm_event_rows)
    event_live = live_list(event_rows, cfg["categories"], alarm_events)

    # 月度（报警口径，记录级）
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

    # 类别内处置指向（多标签，记录级）
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

    merged = len(rows) - len(event_rows)
    pending_reduction = sum(len(g["rows"]) - 1 for g in pending_groups)
    extra_caveat = (
        f"事件级按配置中 {len(event_groups)} 组跨班重复归并：记录 {len(rows)} 条 → 独立事件 "
        f"{len(event_rows)} 起（报警类 {alarm_events} 起）。"
    )
    if pending_groups:
        extra_caveat += (
            f"另有 {len(pending_groups)} 组待确认，若全部采纳，事件数最多再减 {pending_reduction} 起。"
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
            "events": len(event_rows),
            "alarmEvents": alarm_events,
            "merged": merged,
            "top1Pct": event_live[0]["pct"] if event_live else 0,
            "top1Count": event_live[0]["count"] if event_live else 0,
            "top3Cum": event_live[min(2, len(event_live) - 1)]["cum"] if event_live else 0,
        },
        "pareto": event_live,
        "paretoRecord": record_live,
        "months": month_list,
        "monthsPeak": peak,
        "monthsNote": months_note,
        "facets": facets,
        "top3": cfg.get("top3", []),
        "eventInfo": {
            "groups": len(event_groups),
            "merged": merged,
            "pending": len(pending_groups),
            "pendingReduction": pending_reduction,
        },
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
