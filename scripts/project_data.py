#!/usr/bin/env python3
"""File-first project data. Python 3.11+, standard library only.

JSON is authoritative; Markdown and embedded HTML are generated views.
No network, browser cache, or system locale is used as a source of truth.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TZ = timezone(timedelta(hours=8), 'Asia/Shanghai')
PLAN_PATH = 'progress/plan90.json'
FAULT_PATH = 'data/faults.local.json'
PLAN_SCHEMA = 'self-evolution/plan90/v2'
FAULT_SCHEMA = 'self-evolution/faults/v1'
ID_RE = re.compile(r'^[A-Za-z0-9_-]+$')
UNCHECKED = object()  # omitted expectation != explicit None (the file must not exist)
MUSIC_RELEASE_IDS = frozenset(('4-5', '8-2', '13-2'))
DEFAULT_EQ = ['立式炉管', '卧式炉管', '高温退火', 'RTA', '激光退火', 'PECVD', 'SACVD', '溅镀', '蒸镀', '离子注入', '其他']
DEFAULT_CAT = ['真空系统', '气体与化学输送', '温控与热工', 'RF与等离子体', '传片与自动化', '电气与控制', '激光系统', '量测与检测', '耗材与备件', '工艺相关', '软件与通信', '厂务动力', '其他']
TEXT_FIELDS = ['date', 'eqType', 'eqModel', 'eqId', 'alarmCode', 'causeCategory', 'symptom', 'condition',
               'troubleshootPath', 'rootCause', 'rootCauseTag', 'action', 'prevention', 'links', 'notes']
SENSITIVE_FIELDS = ['eqModel', 'eqId', 'alarmCode', 'condition', 'links']


def stamp():
    return datetime.now(TZ).isoformat(timespec='seconds')


def today():
    return datetime.now(TZ).date()


def parse_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError(f'日期必须为 YYYY-MM-DD：{value!r}')
    return date.fromisoformat(value)


def dump(data):
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def load(root, relative):
    return json.loads((Path(root) / relative).read_text(encoding='utf-8'))


def tasks(plan):
    return [t for w in plan['weeks'] for t in w['tasks']]


def task_index(plan):
    return {t['id']: t for t in tasks(plan)}


def calc_stats(plan):
    ts = tasks(plan)
    done = sum(t['done'] for t in ts)
    return {'totalTasks': len(ts), 'doneTasks': done,
            'pct': math.floor(done * 100 / len(ts) + .5) if ts else 0,
            'delivDone': sum(d['done'] for d in plan['deliverables']),
            'delivTotal': len(plan['deliverables'])}


MAX_SAFE_INTEGER = 2**53 - 1


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer_number(value, minimum=0):
    # JSON has a single numeric type. Match JS safe integers, excluding booleans.
    return type(value) in (int, float) and minimum <= value <= MAX_SAFE_INTEGER and value == int(value)


def validation_day(as_of=None):
    return today() if as_of is None else parse_date(as_of)


def validate_state(item, as_of, *, label='记录'):
    """Shared live/import state contract; unknown completion dates stay unknown."""
    require(isinstance(item, dict), f'{label} 必须是对象')
    require(type(item.get('done', False)) is bool, f'{label}.done 必须为布尔值')
    require(isinstance(item.get('note', ''), str), f'{label}.note 必须为文本')
    evidence = item.get('evidence', [])
    require(isinstance(evidence, list) and all(isinstance(x, str) for x in evidence), f'{label}.evidence 必须为文本数组')
    completed = item.get('completedOn')
    require(completed is None or isinstance(completed, str), f'{label}.completedOn 必须为日期或 null')
    if completed:
        require(parse_date(completed) <= as_of, f'{label}.completedOn 不能在未来')
        require(item.get('done', False), f'{label} 未完成却设置完成日期')


def validate_daily_state(checkins, logs, meta, as_of, *, allow_duplicates=False):
    start, end = parse_date(meta['day0']), parse_date(meta['end'])
    require(isinstance(checkins, list), 'checkins 必须为日期数组')
    for ds in checkins:
        d = parse_date(ds)
        require(start <= d <= end and d <= as_of, '打卡日期必须在本计划内且不能在未来')
    require(allow_duplicates or len(set(checkins)) == len(checkins), '打卡日期重复')
    require(isinstance(logs, dict), 'dailyLogs 必须为日期索引对象')
    for ds, log in logs.items():
        d = parse_date(ds)
        require(start <= d <= end and d <= as_of, '每日记录日期必须在本计划内且不能在未来')
        require(isinstance(log, dict) and isinstance(log.get('note', ''), str), '每日记录 / 备注格式无效')
        if 'minutes' in log:
            require(integer_number(log['minutes']), '每日分钟必须为非负整数；未知时不填')


def validate_plan(p, *, as_of=None):
    require(isinstance(p, dict) and p.get('schema') == PLAN_SCHEMA,
            '不是受支持的进度格式；旧备份请使用 import-plan 导入状态。')
    now = validation_day(as_of)
    m = p.get('meta')
    require(isinstance(m, dict), '缺少计划 meta')
    d0, day1, end = parse_date(m.get('day0')), parse_date(m.get('day1')), parse_date(m.get('end'))
    require((day1 - d0).days == 1, 'Day 1 必须是 Day 0 的次日')
    require(integer_number(m.get('totalWeeks'), 1) and integer_number(m.get('totalDays'), 1), '周数 / 总天数必须为正整数')
    weeks = p.get('weeks')
    require(isinstance(weeks, list) and len(weeks) == m['totalWeeks'] and m['totalDays'] == m['totalWeeks'] * 7, '周数 / 总天数不一致')
    require((end - d0).days == m['totalDays'], '结束日期与总天数不一致')
    require(integer_number(m.get('revision')), 'revision 必须是非负整数')
    require(isinstance(m.get('updated'), str), 'meta.updated 必须为文本')
    require((parse_date(m.get('day90')) - d0).days == 90, 'Day 90 日期不一致')
    if 'day98' in m:
        require(m['day98'] == m['end'], 'day98 与 end 不一致')
    tracks = p.get('tracks')
    require(isinstance(tracks, dict) and all(isinstance(v, str) and v for v in tracks.values()), '轨道标签必须为非空文本')
    seen = set()
    for i, w in enumerate(weeks, 1):
        require(isinstance(w, dict), '周安排必须为对象')
        require(integer_number(w.get('n'), 1) and w['n'] == i and
                (parse_date(w.get('start')) - d0).days == (i-1)*7+1 and
                (parse_date(w.get('end')) - d0).days == i*7, f'W{i} 日期不连续')
        require(isinstance(w.get('tasks'), list), f'W{i} 缺少任务数组')
        require(isinstance(w.get('note', ''), str) and isinstance(w.get('title'), str) and isinstance(w.get('days'), str), f'W{i} 标题 / 日号 / 备注格式无效')
        for t in w['tasks']:
            validate_task(t, seen, as_of=now)
            require(isinstance(t.get('track'), str) and t['track'] in tracks, '任务轨道无效')
            scheduled, due = parse_date(t.get('scheduledDate')), parse_date(t.get('dueDate'))
            require(d0 <= scheduled <= due <= end, f'任务 {t["id"]} 排期越界或倒置')
            require(type(t.get('optional', False)) is bool, f'{t["id"]}.optional 必须为布尔值')
    require(isinstance(p.get('deliverables'), list), '缺少交付物数组')
    for d in p['deliverables']:
        validate_task(d, seen, as_of=now)
        require(d0 <= parse_date(d.get('dueDate')) <= end, '交付物截止日不在计划内')
    ti = task_index(p)
    for t in ti.values():
        parents = t.get('dependsOn', [])
        require(isinstance(parents, list) and all(isinstance(x, str) and x in ti and x != t['id'] for x in parents),
                f'任务 {t["id"]} 的前置 ID 无效')
    daily = p.get('dailyPlan')
    require(isinstance(daily, list) and len(daily) == m['totalDays'] + 1, '每日安排必须覆盖 Day 0 至结束日')
    for i, day in enumerate(daily):
        require(isinstance(day, dict) and integer_number(day.get('day')) and day['day'] == i and
                (parse_date(day.get('date')) - d0).days == i, '每日安排存在缺日或重复')
        require(integer_number(day.get('budgetMinutes')) and isinstance(day.get('actions'), list), '每日预算 / 动作无效')
        for action in day['actions']:
            require(isinstance(action, dict) and isinstance(action.get('taskId'), str) and action['taskId'] in ti and
                    isinstance(action.get('text'), str), '每日动作引用不存在的任务')
    validate_daily_state(p.get('checkins'), p.get('dailyLogs', {}), m, now)
    overrides = p.get('overrides', [])
    require(isinstance(overrides, list), 'overrides 必须为数组')
    for override in overrides:
        require(isinstance(override, dict), '模式安排必须为对象')
        require(d0 <= parse_date(override.get('start')) <= parse_date(override.get('end')) <= end and
                override.get('mode') in ('night', 'low') and isinstance(override.get('note', ''), str), '豁免日期或模式无效')
    require(isinstance(p.get('checkpoints'), list), '缺少复检点数组')
    for point in p['checkpoints']:
        require(isinstance(point, dict) and integer_number(point.get('day')) and point['day'] <= m['totalDays'] and
                (parse_date(point.get('date')) - d0).days == point['day'] and isinstance(point.get('text'), str), '复检点日期与 Day 编号不一致')
    for key in ('history', '_orphans'):
        require(isinstance(p.get(key, []), list), f'{key} 必须为数组')
    expected, actual = calc_stats(p), p.get('stats')
    require(isinstance(actual, dict) and set(actual) == set(expected) and
            all(integer_number(actual[k]) and actual[k] == v for k, v in expected.items()), 'stats 与任务状态不一致；请重新计算后保存')


def validate_task(t, seen, *, as_of=None):
    require(isinstance(t, dict), '任务必须为对象')
    tid = t.get('id')
    require(isinstance(tid, str) and ID_RE.fullmatch(tid) and tid not in seen, '任务 ID 无效或重复')
    seen.add(tid)
    require('done' in t and isinstance(t.get('text'), str), f'{tid} 缺少状态 / 文字')
    validate_state(t, today() if as_of is None else as_of, label=tid)


def empty_faults():
    return {'schema': FAULT_SCHEMA,
            'meta': {'title': '设备故障模式库', 'timezone': 'Asia/Shanghai', 'revision': 0,
                     'updated': '2026-09-06', 'nextId': 1, 'stateOwner': FAULT_PATH},
            'items': [], 'config': {'eqTypes': DEFAULT_EQ.copy(), 'categories': DEFAULT_CAT.copy(), 'sensitive': []},
            'history': []}


def validate_faults(data):
    if not isinstance(data, dict) or data.get('schema') != FAULT_SCHEMA or not isinstance(data.get('items'), list):
        raise ValueError('不是受支持的故障库格式')
    require(isinstance(data.get('meta'), dict) and integer_number(data['meta'].get('revision')), '故障库缺少有效 revision')
    if 'nextId' in data['meta']:
        require(integer_number(data['meta']['nextId'], 1), 'nextId 必须为正整数')
    seen = set()
    for item in data['items']:
        require(isinstance(item, dict), '故障记录必须为对象')
        tid = item.get('id')
        if not isinstance(tid, str) or not ID_RE.fullmatch(tid) or tid in seen:
            raise ValueError(f'故障 ID 无效或重复：{tid!r}')
        seen.add(tid)
        for f in TEXT_FIELDS:
            if f in item and not isinstance(item[f], str):
                raise ValueError(f'{tid}.{f} 必须是文本')
        ds = item.get('date', '')
        if ds:
            if re.fullmatch(r'\d{4}-\d{2}', ds):
                parse_date(ds + '-01')  # old sanitized backups preserve only a month
            else:
                parse_date(ds)
        for key in ('isRecurring', 'isSolved', 'isSample'):
            if key in item and item[key] is not None and type(item[key]) is not bool:
                raise ValueError(f'{tid}.{key} 必须为布尔值或 null')
        n = item.get('downtimeMin')
        if n is not None and (type(n) not in (int, float) or not math.isfinite(n) or n < 0):
            raise ValueError(f'{tid} 停机时长必须为非负数或 null')
    require(isinstance(data.get('config'), dict), '故障配置必须为对象')
    for key in ('eqTypes', 'categories', 'sensitive'):
        val = data['config'].get(key)
        if not isinstance(val, list) or any(not isinstance(x, str) for x in val):
            raise ValueError(f'config.{key} 必须是文本数组')


def is_sample(item):
    return bool(item.get('isSample')) or str(item.get('id', '')).startswith('sample') or '【示例' in item.get('symptom', '')


def real_faults(data):
    return [i for i in data['items'] if not is_sample(i)]


def normalize_fault_record(payload, rid, at):
    obj = {f: '' for f in TEXT_FIELDS}
    obj.update({'isRecurring': None, 'isSolved': None, 'downtimeMin': None, 'isSample': False})
    obj.update(copy.deepcopy(payload))  # unknown fields are preserved, never silently dropped
    obj.update({'id': rid, 'updatedAt': at})
    obj.setdefault('createdAt', at)
    if not any(obj.get(k, '').strip() for k in ('symptom', 'alarmCode', 'rootCause')):
        raise ValueError('至少记录现象、报警或根因之一；未知内容留空，不能编造')
    return obj


def event(data, action, **details):
    data.setdefault('history', []).append({'at': stamp(), 'action': action, **details})


def atomic_write(path, text, *, expected=UNCHECKED, backup=False):
    """Compare-and-replace with a cooperative lock and 20 rollback copies.

    expected is the exact previously read text; None means the file was absent.
    Omitting expected permits intentional replacement of a generated view.
    File System Access API uses the same read-before-write rule in the browser.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + '.lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError(f'{path.name} 正在写入；稍后重试。若进程异常退出，确认无写入后再删除 .lock。') from exc
    os.close(fd)
    temp_name = None
    try:
        old = path.read_text(encoding='utf-8') if path.exists() else None
        if expected is not UNCHECKED and old != expected:
            raise ValueError(f'{path.name} 已被其他操作更新，请重新读取，未覆盖文件')
        if old == text:
            return
        if backup and old is not None:
            directory = path.parent / '.backups'
            directory.mkdir(exist_ok=True)
            suffix = datetime.now(TZ).strftime('%Y%m%dT%H%M%S%f')
            (directory / f'{path.stem}.{suffix}.json').write_text(old, encoding='utf-8')
            for stale in sorted(directory.glob(path.stem + '.*.json'))[:-20]:
                stale.unlink()
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n', dir=path.parent,
                                         prefix='.' + path.name + '.', suffix='.tmp', delete=False) as f:
            temp_name = f.name
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name and Path(temp_name).exists():
            Path(temp_name).unlink()
        lock.unlink(missing_ok=True)


def save_data(root, relative, data, original):
    data['meta']['revision'] = data['meta'].get('revision', 0) + 1
    data['meta']['updated'] = stamp()
    if relative == PLAN_PATH:
        mapping = Path(root) / '01-个人档案.local.md'
        if mapping.exists():
            content = dump(data)
            for _, value in re.findall(r'^\|\s*(.+?)\s*\|\s*(.+?)\s*\|', mapping.read_text(encoding='utf-8'), re.M):
                value = value.strip()
                if value and not value.startswith(('真值', '---', '（')) and value in content:
                    raise ValueError('公开进度含本地映射真值，已拒绝写入；请用代称或记到私有故障文件')
        data['stats'] = calc_stats(data)
        validate_plan(data)
    else:
        validate_faults(data)
    atomic_write(Path(root) / relative, dump(data), expected=original, backup=True)


def day_info(p, ds, mode=None):
    d = parse_date(ds)
    number = (d - parse_date(p['meta']['day0'])).days
    current = next((x for x in p['dailyPlan'] if x['date'] == ds), None)
    overrides = [x for x in p.get('overrides', []) if x['start'] <= ds <= x['end']]
    mode = mode or ('night' if any(x['mode'] == 'night' for x in overrides)
                    else 'low' if overrides else 'normal')
    idx = task_index(p)
    overdue = [t for t in tasks(p) if not t['done'] and t['dueDate'] < ds and not t.get('optional')]
    candidates = []
    if current:
        for a in current['actions']:
            if not idx[a['taskId']]['done']:
                candidates.append({**a, 'dueDate': idx[a['taskId']]['dueDate'], 'optional': idx[a['taskId']].get('optional', False)})
    # An unfinished prerequisite takes priority over the next sound task. Never stack an entire backlog.
    blocked = False
    active_candidate = next((a for a in candidates if not a['optional']), candidates[0] if candidates else None)
    if active_candidate:
        pending = [idx[x] for x in idx[active_candidate['taskId']].get('dependsOn', []) if not idx[x]['done']]
        if pending:
            t = pending[0]
            if t['id'] != active_candidate['taskId']:
                candidates.insert(0, {'taskId': t['id'], 'text': '先推进前置任务：' + t['text'] + '（只做一小步，不要求一次补完）',
                                      'dueDate': t['dueDate'], 'optional': False})
                blocked = True
    if not candidates and 1 <= number <= p['meta']['totalDays']:
        remaining = sorted([t for t in tasks(p) if not t['done'] and not t.get('optional') and t['scheduledDate'] <= ds],
                           key=lambda t: (t['dueDate'], t['id']))
        if remaining:
            t = remaining[0]
            candidates = [{'taskId': t['id'], 'text': '推进未完的一小步：' + t['text'], 'dueDate': t['dueDate'], 'optional': False}]
    music_overdue = any(t['track'] == 'sound' or t['id'] in MUSIC_RELEASE_IDS for t in overdue) or any(
        d['id'].startswith('song') and not d['done'] and d['dueDate'] < ds for d in p['deliverables'])
    if music_overdue:
        candidates = [a for a in candidates if idx[a['taskId']]['track'] != 'ipa']
    if mode == 'night':
        candidates = []
    elif mode == 'low':
        candidates = [a for a in candidates if not a['optional']][:1]
    else:
        candidates = candidates[:3]
    return {'date': ds, 'day': number, 'week': (number - 1)//7 + 1 if 1 <= number <= p['meta']['totalDays'] else None,
            'mode': mode, 'actions': candidates, 'overdueCount': len(overdue), 'prerequisiteFirst': blocked,
            'budgetMinutes': 10 if mode == 'night' else 25 if mode == 'low' else current['budgetMinutes'] if current else 0,
            'checkpoints': [c for c in p['checkpoints'] if c['date'] == ds],
            'checkedIn': ds in p['checkins'], 'ipaPaused': music_overdue}


def safe_md(text):
    return str(text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '\\|').replace('\n', '<br>')


def overview_md(p):
    m, s = p['meta'], p['stats']
    lines = ['# 进度总览 · Self-Evolution', '',
             '> 自动生成，只读。唯一记录源：[`plan90.json`](plan90.json)。不要手改勾选；直接告诉 agent。',
             f'> 状态最后更新：{m["updated"]} · revision {m["revision"]} · 时区 Asia/Shanghai', '',
             f'**任务 {s["doneTasks"]}/{s["totalTasks"]}（{s["pct"]}%） · 交付物 {s["delivDone"]}/{s["delivTotal"]} · 打卡 {len(p["checkins"])} 天**', '',
             f'**Day 0：{m["day0"]}（周日） · Day 1：{m["day1"]}（周一） · Day 90：{m["day90"]} · Day 98 / 收尾：{m["end"]}**', '',
             '## 使用约定', '',
             '- 日期是计划，不是完成证明；到期不会自动勾选。每天只选一个优先动作，做 25 分钟也算达标。',
             '- 故障真实记录见本地 `../data/faults.local.json` / `../data/故障模式库.local.md`；不写入公开进度备注。',
             '- W5 / W10 是浮动缓冲位，不代表已确认夜班。实际夜班由 agent 写入豁免日期；不补作业、不伪造打卡。',
             '- 每日表中的动作是建议拆分，不另外计分；整项完成状态以稳定任务 ID 的勾选为准。', '', '## 复检日历', '',
             '| 日期 | 日号 | 验收 |', '|---|---|---|']
    for c in p['checkpoints']:
        lines.append(f'| {c["date"]} | Day {c["day"]} | {safe_md(c["text"])} |')
    lines += ['', '## 最终交付物', '']
    for d in p['deliverables']:
        lines.append(f'- [{"x" if d["done"] else " "}] **{d["id"]} · {safe_md(d["text"])}** · {d["dueDate"]} 前 · {safe_md(d["sub"])}')
        lines.extend(item_details(d))
    prep = p['dailyPlan'][0]
    lines += ['', '## Day 0 · 2026-09-06 · 可选准备（≤15 分钟）', '']
    for a in prep['actions']:
        lines.append(f'- `{a["taskId"]}` {safe_md(a["text"])}')
    lines += ['', '这些动作若提前做完，勾同一个 W1 任务即可，不重复计分。']
    for w in p['weeks']:
        done = sum(t['done'] for t in w['tasks'])
        lines += ['', f'## W{w["n"]} · {w["start"]}—{w["end"]} · Day {w["days"]}', '',
                  f'**{safe_md(w["title"])} · {done}/{len(w["tasks"])} 项**', '']
        if w.get('warn'):
            lines += ['> ' + safe_md(w['warn']), '']
        if w.get('note'):
            lines += ['**周备注：** ' + safe_md(w['note']), '']
        for t in w['tasks']:
            flag = ' · 可暂停/条件任务' if t.get('optional') else ''
            lines.append(f'- [{"x" if t["done"] else " "}] **`{t["id"]}`** [{p["tracks"][t["track"]]}] {safe_md(t["text"])}')
            lines.append(f'  - 排期 {t["scheduledDate"]} → **{t["dueDate"]}**{flag}；验收：{safe_md(t["output"])}')
            lines.extend(item_details(t))
        lines += ['', '### 每日建议（与上面的任务共用状态）', '', '| 日期 | 星期 | 优先动作 / 顺带动作 |', '|---|---|---|']
        for d in p['dailyPlan']:
            if w['start'] <= d['date'] <= w['end']:
                actions = '；'.join(f'`{a["taskId"]}` {safe_md(a["text"])}' for a in d['actions'])
                lines.append(f'| {d["date"]} | {"一二三四五六日"[parse_date(d["date"]).weekday()]} | {actions or "只做最低剂量；已有任务收尾"} |')
    lines += ['', '## 打卡与每日记录', '']
    if not p['checkins']:
        lines += ['尚无打卡。整理工具或打开文件，不算你已经学习。']
    else:
        lines += ['| 日期 | 分钟 | 记录 |', '|---|---|---|']
        for ds in sorted(p['checkins']):
            log = p.get('dailyLogs', {}).get(ds, {})
            lines.append(f'| {ds} | {log.get("minutes", "—")} | {safe_md(log.get("note", ""))} |')
    if p.get('overrides'):
        lines += ['', '## 已确认的低能 / 夜班日期', '']
        for x in p['overrides']:
            lines.append(f'- {x["start"]}—{x["end"]} · {x["mode"]} · {safe_md(x.get("note", ""))}')
    lines += ['', '## 最近变更（最多 20 条；完整记录在 JSON）', '']
    for e in p.get('history', [])[-20:]:
        lines.append(f'- {e["at"]} · {safe_md(e["action"])} · {safe_md(e.get("summary", ", ".join(e.get("ids", []))))}')
    return '\n'.join(lines) + '\n'


def item_details(item):
    lines = []
    if item.get('completedOn'):
        lines.append('  - 确认完成：' + item['completedOn'])
    if item.get('note'):
        lines.append('  - 备注：' + safe_md(item['note']))
    if item.get('evidence'):
        lines.append('  - 证据：' + ' · '.join(safe_md(e) for e in item['evidence']))
    return lines


def fault_md(data):
    lines = ['# 故障模式库 · 本地私有视图', '', '> 自动生成；仅供本地查看，不进入公开 Git 仓库。唯一记录源：`faults.local.json`。',
             '> 原始记录不等于经验证的安全操作规程；现场以批准的 SOP / interlock / 安全要求为准。',
             f'> 状态最后更新：{data["meta"]["updated"]} · revision {data["meta"]["revision"]}', '',
             f'**真实记录：{len(real_faults(data))} / 30；示例不计入成果。**', '']
    if not data['items']:
        lines += ['尚未录入真实故障。直接向 agent 描述亲身处理的故障即可；未知根因、停机时长和解决状态留空待确认。']
    labels = {'date': '发生日期', 'eqType': '机台类型', 'eqModel': '机台型号（敏感）', 'eqId': '机台编号（敏感）', 'alarmCode': '报警码（敏感）',
              'causeCategory': '故障类别', 'symptom': '现象', 'condition': '发生条件（敏感）', 'troubleshootPath': '排查路径',
              'rootCause': '根因', 'rootCauseTag': '根因标签', 'action': '处理', 'prevention': '预防 / 改善', 'links': '相关文件（敏感）', 'notes': '备注'}
    for i in data['items']:
        lines += ['', f'## {i["id"]} · {safe_md(i.get("symptom") or "待补现象")}' + ('【示例】' if is_sample(i) else ''), '']
        for field, label in labels.items():
            lines.append(f'- **{label}**：{safe_md(i.get(field)) or "待确认 / 未提供"}')
        for f, label in [('isRecurring', '是否复发'), ('isSolved', '是否彻底解决')]:
            lines.append(f'- **{label}**：' + ('待确认' if i.get(f) is None else '是' if i[f] else '否'))
        lines.append(f'- **停机分钟**：{i.get("downtimeMin") if i.get("downtimeMin") is not None else "待确认"}')
        extras = {k: v for k, v in i.items() if k not in set(TEXT_FIELDS + ['id', 'createdAt', 'updatedAt', 'isRecurring', 'isSolved', 'downtimeMin', 'isSample'])}
        if extras:
            lines += ['', '附加字段（原样保留）：', '', '```json', dump(extras).rstrip(), '```']
    return '\n'.join(lines) + '\n'


def execution_block(p):
    lines = ['<!-- PLAN-SCHEDULE:BEGIN -->', '> 本节由 `progress/plan90.json` 生成；改排期由 agent 改 JSON 后同步，不在此维护状态。',
             '> **每日动作、勾选、备注和证据 → [`progress/进度总览.md`](progress/进度总览.md)。**',
             '> 夜班日期未确认；W5 / W10 仅预留缓冲。实际夜班只保留墨墨 10 分钟，其余暂停，不自动算完成。', '']
    for w in p['weeks']:
        lines += [f'### W{w["n"]} · Day {w["days"]}（{w["start"]}—{w["end"]}）· {w["title"]}', '',
                  '| 截止日 | 轨道 / ID | 动作 | 验收产出 |', '|---|---|---|---|']
        for t in w['tasks']:
            lines.append(f'| {t["dueDate"]} | {p["tracks"][t["track"]]} `{t["id"]}` | {safe_md(t["text"])}{"（可暂停 / 条件执行）" if t.get("optional") else ""} | {safe_md(t["output"])} |')
        if w.get('warn'):
            lines += ['', '> ' + w['warn']]
        lines += ['']
    lines.append('<!-- PLAN-SCHEDULE:END -->')
    return '\n'.join(lines)


def embedded_json(data):
    # Raw-text script parsing must never see user-supplied </script> or HTML markup.
    return dump(data).rstrip().replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')


def block_bounds(text, start, end):
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f'生成标记缺失或重复：{start}')
    a, b = text.index(start), text.index(end)
    if a + len(start) > b:
        raise ValueError(f'生成标记顺序错误：{start}')
    return a, b + len(end)


def replace_block(text, start, end, content):
    a, b = block_bounds(text, start, end)
    return text[:a + len(start)] + '\n' + content.rstrip() + '\n' + text[b - len(end):]


def sync_views(root=ROOT, check=False):
    root = Path(root)
    p = load(root, PLAN_PATH)
    validate_plan(p)
    bridge = (root / 'scripts/file-store.js').read_text(encoding='utf-8')
    outputs = {root / 'progress/进度总览.md': overview_md(p)}
    for name, data in [('90天进度表.html', p), ('故障模式库.html', empty_faults())]:
        path = root / 'tools' / name
        html = path.read_text(encoding='utf-8')
        html = replace_block(html, '<script type="application/json" id="project-data">', '</script><!-- PROJECT-DATA:END -->', embedded_json(data))
        html = replace_block(html, '/* FILE-STORE:BEGIN */', '/* FILE-STORE:END */', bridge)
        outputs[path] = html
    source = root / '03-90天计划.md'
    text = source.read_text(encoding='utf-8')  # a missing required template must fail too
    start, end = '<!-- PLAN-SCHEDULE:BEGIN -->', '<!-- PLAN-SCHEDULE:END -->'
    a, b = block_bounds(text, start, end)
    outputs[source] = text[:a] + execution_block(p) + text[b:]
    if (root / FAULT_PATH).exists():
        faults = load(root, FAULT_PATH)
        validate_faults(faults)
        outputs[root / 'data/故障模式库.local.md'] = fault_md(faults)
        local = replace_block(outputs[root / 'tools/故障模式库.html'], '<script type="application/json" id="project-data">', '</script><!-- PROJECT-DATA:END -->', embedded_json(faults))
        local = local.replace('<title>设备故障模式库', '<title>本地私有 · 设备故障模式库').replace('data-private="false"', 'data-private="true"')
        outputs[root / 'tools/故障模式库.local.html'] = local
    stale = []
    for path, text in outputs.items():
        if not path.exists() or path.read_text(encoding='utf-8') != text:
            stale.append(str(path.relative_to(root)))
            if not check:
                atomic_write(path, text)
    return stale


def sanitize_faults(data, extra_words=()):
    # Explicit allowlist: no IDs, timestamps, config, history, links, or unknown fields escape.
    allowed = ['date', 'eqType', 'causeCategory', 'symptom', 'troubleshootPath', 'rootCause',
               'rootCauseTag', 'action', 'prevention', 'notes', 'downtimeMin', 'isRecurring', 'isSolved']
    words = set(data['config'].get('sensitive', [])) | set(extra_words)
    for item in data['items']:
        words.update(item.get(k, '') for k in SENSITIVE_FIELDS)
    words.discard('')
    patterns = [re.compile(re.escape(w), re.I) for w in sorted(words, key=len, reverse=True)]
    def clean(v):
        if isinstance(v, str):
            for pat in patterns:
                v = pat.sub('***', v)
        return v
    out = []
    for item in real_faults(data):
        obj = {k: clean(item[k]) for k in allowed if k in item}
        if obj.get('date'):
            obj['date'] = obj['date'][:7]
        out.append(obj)
    return {'note': '脱敏候选稿，不是公开许可；自由文本仍须人工复核，确认厂规允许后再分享。', 'items': out}
