#!/usr/bin/env python3
"""Agent entry point. Run from any directory; no third-party dependencies."""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

from project_data import (ROOT, PLAN_PATH, FAULT_PATH, PLAN_SCHEMA, FAULT_SCHEMA, TEXT_FIELDS,
                          load, dump, today, stamp, parse_date, tasks, task_index, calc_stats,
                          validate_plan, validate_faults, empty_faults, real_faults, is_sample,
                          normalize_fault_record, event, save_data, sync_views, day_info,
                          sanitize_faults, atomic_write, require, integer_number, ID_RE,
                          validation_day, validate_state, validate_daily_state)


def get_document(root, relative):
    path = root / relative
    if not path.exists() and relative == FAULT_PATH:
        return empty_faults(), None
    raw = path.read_text(encoding='utf-8')
    return json.loads(raw), raw


def finish(root, relative, data, original):
    save_data(root, relative, data, original)
    try:
        sync_views(root)
    except Exception as exc:
        raise ValueError(f'JSON 已保存，但只读视图生成失败：{exc}。请运行 sync-plan.py；不要重复录入。') from exc
    print(f'已写入 {relative} · revision {data["meta"]["revision"]}；只读视图已同步。')


def date_used(value):
    ds = value or today().isoformat()
    if parse_date(ds) > today():
        raise ValueError('完成 / 打卡日期不能写到未来；提前完成请记实际完成日期')
    return ds


def select_items(p, ids):
    idx = {x['id']: x for x in tasks(p) + p['deliverables']}
    missing = [x for x in ids if x not in idx]
    if missing:
        raise ValueError('未找到 ID：' + ', '.join(missing) + '；未修改任何任务')
    return [idx[x] for x in dict.fromkeys(ids)]


def merge_notes(a, b):
    a, b = str(a or ''), str(b or '')
    # Match a complete line block, not an arbitrary substring or only one line.
    return a if not b or '\n' + b + '\n' in '\n' + a + '\n' else a + ('\n' if a else '') + b


def import_plan_state(p, payload, *, as_of=None):
    """Validate the whole incoming state before committing an in-memory merge.

    Schedule/current unknown fields stay in the master; true completions are OR
    merged, notes/evidence are additive, and unknown IDs are archived. Invalid
    state rejects the entire import; neither the caller's object nor files change.
    """
    now = validation_day(as_of)
    validate_plan(p, as_of=now.isoformat())
    require(isinstance(payload, dict), '备份必须是 JSON 对象')
    schema = payload.get('schema')
    require(schema in (None, PLAN_SCHEMA, 'self-evolution/plan90/v1'), '不是受支持的进度备份 schema')
    imported, week_notes, deliveries = [], {}, []
    if schema in (PLAN_SCHEMA, 'self-evolution/plan90/v1'):
        weeks = payload.get('weeks')
        require(isinstance(weeks, list), '旧备份缺少 weeks 数组')
        seen_weeks = set()
        for w in weeks:
            require(isinstance(w, dict) and integer_number(w.get('n'), 1) and isinstance(w.get('tasks'), list), '导入周格式无效')
            key = str(int(w['n']))
            require(key not in seen_weeks, '导入周次重复')
            seen_weeks.add(key)
            require(isinstance(w.get('note', ''), str), '导入周备注必须为文本')
            imported.extend(w['tasks'])
            if w.get('note'):
                week_notes[key] = w['note']
        deliveries = payload.get('deliverables', [])
        require(isinstance(deliveries, list), '导入交付物必须为数组')
    else:
        done, notes, deliv = payload.get('done'), payload.get('notes', {}), payload.get('deliv', {})
        require(isinstance(done, dict) and isinstance(notes, dict) and isinstance(deliv, dict), '不是受支持的旧浏览器状态')
        require(all(isinstance(k, str) and isinstance(v, str) for k, v in notes.items()), '旧备注必须是文本索引')
        week_notes = {k: v for k, v in notes.items() if re.fullmatch(r'[1-9][0-9]*', k)}
        note_ids = [k for k in notes if k not in week_notes and k not in deliv]
        ids = list(dict.fromkeys(list(done) + note_ids))
        imported = [{'id': k, 'done': done.get(k, False), 'note': notes.get(k, '')} for k in ids]
        deliveries = [{'id': k, 'done': v, 'note': notes.get(k, '')} for k, v in deliv.items()]
    seen = set()
    for src in imported + deliveries:
        require(isinstance(src, dict), '导入任务必须为对象')
        tid = src.get('id')
        require(isinstance(tid, str) and ID_RE.fullmatch(tid) and tid not in seen, '导入中存在重复 / 无效 ID')
        seen.add(tid)
        # Validate even unknown IDs or values that would lose to newer master data.
        validate_state(src, now, label='导入记录 ' + tid)
    checkins, logs = payload.get('checkins', []), payload.get('dailyLogs', {})
    validate_daily_state(checkins, logs, p['meta'], now, allow_duplicates=True)
    orphans = payload.get('_orphans', [])
    require(isinstance(orphans, list), '_orphans 必须为数组')
    for src in orphans:
        validate_state(src, now, label='导入归档记录')

    candidate = copy.deepcopy(p)
    idx = {x['id']: x for x in tasks(candidate) + candidate['deliverables']}
    archive = candidate.setdefault('_orphans', [])
    def keep(record):
        if record not in archive:
            archive.append(copy.deepcopy(record))
    for src in imported + deliveries:
        tid = src['id']
        if tid not in idx:
            keep(src)
            continue
        dst = idx[tid]
        dst['done'] = dst['done'] or src.get('done', False)
        dst['note'] = merge_notes(dst.get('note'), src.get('note'))
        dst['evidence'] = list(dict.fromkeys(dst.get('evidence', []) + src.get('evidence', [])))
        if dst['done'] and not dst.get('completedOn') and src.get('completedOn'):
            dst['completedOn'] = src['completedOn']
    weeks = {str(int(w['n'])): w for w in candidate['weeks']}
    for n, note in week_notes.items():
        if n in weeks:
            weeks[n]['note'] = merge_notes(weeks[n].get('note'), note)
        elif note:
            keep({'id': 'week-' + n, 'kind': 'week-note', 'note': note})
    candidate['checkins'] = sorted(set(candidate['checkins']) | set(checkins))
    for ds, log in logs.items():
        dest = candidate.setdefault('dailyLogs', {}).setdefault(ds, {})
        dest['note'] = merge_notes(dest.get('note'), log.get('note'))
        for key, value in log.items():
            if key not in dest:
                dest[key] = copy.deepcopy(value)
    for src in orphans:
        keep(src)
    candidate['stats'] = calc_stats(candidate)
    validate_plan(candidate, as_of=now.isoformat())
    # One commit point: all parsing, validation and merge work succeeded.
    p.clear()
    p.update(candidate)
    return len(seen)


def show_today(p, faults, args):
    ds = args.date or today().isoformat()
    info = day_info(p, ds, args.mode)
    if args.json:
        print(dump({**info, 'stats': p['stats'], 'realFaultCount': len(real_faults(faults)), 'habits': p['habits']}), end='')
        return
    d, w = info['day'], info['week']
    weekday = '一二三四五六日'[parse_date(ds).weekday()]
    print(f'{ds}（周{weekday}） · Day {d}' + (f' · W{w}' if w else ''))
    print(f'文件状态：任务 {p["stats"]["doneTasks"]}/{p["stats"]["totalTasks"]}；交付 {p["stats"]["delivDone"]}/{p["stats"]["delivTotal"]}；真实故障 {len(real_faults(faults))} 条。')
    if d < 0:
        print(f'尚未进入准备日。Day 0 = {p["meta"]["day0"]}，不把之前的日期都叫 Day 0。')
        return
    if d > p['meta']['totalDays']:
        print('14 周排期已结束。请复盘实际交付与未完成项；不自动滚动成新的一周或自动勾选。')
        return
    if d == 0:
        print('准备日：以下均可选，最多 15 分钟；不必打开网页或打卡，也不用额外折腾工具。')
    elif info['mode'] == 'night':
        print('已按夜班降档：' + p['habits']['night'])
    else:
        print(p['habits']['normal'])
        print('低能日只推进第 1 项，不加量。' if info['mode'] == 'low' else f'建议可用时间上限 {info["budgetMinutes"]} 分钟（不是必须做满）。')
    if info['ipaPaused'] and info['mode'] != 'night':
        print('IPA 已暂停：音乐制作、歌曲发布或交付验收有到期未确认项；先核对音乐闭环。')
    for i, a in enumerate(info['actions'], 1):
        print(f'{i}. [{a["taskId"]}] {a["text"]}' + ('（可选，可暂停）' if a.get('optional') else ''))
    if d > 0 and not info['actions'] and info['mode'] != 'night':
        print('当天没有可追加的建议；有逾期项先核对与收缩，否则保持最低剂量或休息，不强加未来任务。')
    for c in info['checkpoints']:
        print('复检：' + c['text'])
    if info['overdueCount'] and info['mode'] != 'night':
        print(f'另有 {info["overdueCount"]} 项到期未确认；不要求一天补齐，必要时先收缩 / 重排。')
    print('已打卡。' if info['checkedIn'] else '尚未打卡；仅查询不会产生打卡或完成记录。')
    print('完成每日拆分的一小步只记备注；完成整项且你已明确确认，才勾对应 ID。')


def read_payload(args):
    if args.file:
        return json.loads(Path(args.file).read_text(encoding='utf-8-sig'))
    return json.loads(args.data)


def fault_command(root, args):
    data, raw = get_document(root, FAULT_PATH)
    validate_faults(data)
    cmd = args.fault_command
    if cmd in ('list', 'show'):
        selected = data['items']
        if cmd == 'show':
            selected = [i for i in selected if i['id'] == args.id]
            if not selected:
                raise ValueError('未找到故障 ID')
            print(dump(selected[0]), end='')
        else:
            if args.query:
                q = args.query.casefold()
                selected = [i for i in selected if q in json.dumps(i, ensure_ascii=False).casefold()]
            print(f'真实记录 {len(real_faults(data))} 条；当前匹配 {len(selected)} 条（示例不计成果）')
            for i in selected:
                print(f'{i["id"]} · {i.get("date") or "日期待确认"} · {i.get("eqType", "")} · {i.get("symptom", "")}' + ('【示例】' if is_sample(i) else ''))
        return
    if cmd == 'export-sanitized':
        if not args.reviewed:
            raise ValueError('请确认这是待人工复核的候选稿，并添加 --reviewed；它不代表已经取得公开许可')
        output = Path(args.output).resolve()
        if not output.name.endswith('.local.json'):
            raise ValueError('脱敏候选稿仍必须命名为 *.local.json，人工复核通过前不写公开文件')
        if output in ((root / FAULT_PATH).resolve(), (root / PLAN_PATH).resolve()):
            raise ValueError('不能用脱敏稿覆盖原始记录或进度')
        extra = []
        mapping = root / '01-个人档案.local.md'
        if mapping.exists():
            import re
            for _, val in re.findall(r'^\|\s*(.+?)\s*\|\s*(.+?)\s*\|', mapping.read_text(encoding='utf-8'), re.M):
                if not val.startswith(('真值', '---', '（')):
                    extra.append(val.strip())
        atomic_write(output, dump(sanitize_faults(data, extra)), backup=True)
        print('已生成脱敏候选稿：' + str(output) + '。自由文本仍须人工复核。')
        return
    if cmd == 'add':
        payload = read_payload(args)
        if not isinstance(payload, dict):
            raise ValueError('新增故障需要一个 JSON 对象')
        n = int(data['meta'].get('nextId', 1))
        ids = {i['id'] for i in data['items']}
        while f'FM-{n:04d}' in ids:
            n += 1
        rid = f'FM-{n:04d}'
        data['items'].append(normalize_fault_record(payload, rid, stamp()))
        data['meta']['nextId'] = n + 1
        event(data, 'fault-add', ids=[rid])
        finish(root, FAULT_PATH, data, raw)
        print(f'新增 {rid}；真实记录 {len(real_faults(data))} 条。未自动勾选任何学习任务。')
    elif cmd == 'update':
        payload = read_payload(args)
        old = next((i for i in data['items'] if i['id'] == args.id), None)
        if old is None:
            raise ValueError('未找到故障 ID；未修改文件')
        if not isinstance(payload, dict) or ('id' in payload and payload['id'] != args.id):
            raise ValueError('补充记录必须为对象，且不得更换稳定 ID')
        before = copy.deepcopy(old)
        old.update(payload)
        old['updatedAt'] = stamp()
        event(data, 'fault-update', ids=[args.id], before=before)
        finish(root, FAULT_PATH, data, raw)
    elif cmd == 'delete':
        if not args.confirm:
            raise ValueError('删除需用户明确同意，再加 --confirm')
        old = next((i for i in data['items'] if i['id'] == args.id), None)
        if old is None:
            raise ValueError('未找到故障 ID')
        data['items'] = [i for i in data['items'] if i['id'] != args.id]
        event(data, 'fault-delete', ids=[args.id], before=old)
        finish(root, FAULT_PATH, data, raw)
    elif cmd == 'import':
        src = read_payload(args)
        if not isinstance(src, dict) or not isinstance(src.get('items'), list):
            raise ValueError('备份必须包含 items 数组；不清空现有内容')
        if src.get('schema') and src['schema'] != FAULT_SCHEMA:
            raise ValueError('故障库 schema 不兼容')
        # Validate incoming types before normalizing legacy sample markers;
        # otherwise a malformed isSample string could be coerced into a boolean.
        incoming = empty_faults()
        incoming['items'] = src['items']
        require(isinstance(src.get('config', {}), dict), '导入配置必须为对象')
        incoming['config'].update(src.get('config', {}))
        validate_faults(incoming)
        idx = {i['id']: i for i in data['items']}
        seen, count = set(), 0
        for source in src['items']:
            rid = source.get('id')
            if not rid or rid in seen:
                raise ValueError('备份存在重复或缺失的 ID')
            seen.add(rid)
            record = copy.deepcopy(source)
            if is_sample(record):
                record['isSample'] = True
            if rid in idx:
                if record != idx[rid]:
                    raise ValueError(f'{rid} 与当前记录冲突；请先对比，再显式 update，不覆盖')
                continue
            data['items'].append(record)
            count += 1
        for key in ('eqTypes', 'categories', 'sensitive'):
            extra = src.get('config', {}).get(key, [])
            if not isinstance(extra, list) or any(not isinstance(x, str) for x in extra):
                raise ValueError('导入配置必须为文本数组')
            data['config'][key] = list(dict.fromkeys(data['config'][key] + extra))
        event(data, 'fault-import', summary=f'新增 {count} 条；同 ID 内容冲突会拒绝')
        finish(root, FAULT_PATH, data, raw)
        print(f'导入 {count} 条；真实记录 {len(real_faults(data))} 条。')


def build_parser():
    parser = argparse.ArgumentParser(description='Self-Evolution：由 agent 操作的文件进度与故障库')
    parser.add_argument('--root', type=Path, default=ROOT, help='项目根目录（测试 / 迁移时使用）')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('today', help='只读查询；默认按 Asia/Shanghai 计算日期')
    p.add_argument('--date'); p.add_argument('--mode', choices=['normal', 'low', 'night']); p.add_argument('--json', action='store_true')
    for name in ('done', 'undo'):
        p = sub.add_parser(name, help='完成 / 撤销稳定 ID；可一次多项')
        p.add_argument('ids', nargs='+'); p.add_argument('--on'); p.add_argument('--note', default=''); p.add_argument('--evidence', action='append', default=[])
    p = sub.add_parser('note'); p.add_argument('id'); p.add_argument('--text', required=True)
    p = sub.add_parser('week-note'); p.add_argument('week', type=int); p.add_argument('--text', required=True)
    p = sub.add_parser('checkin'); p.add_argument('--on'); p.add_argument('--minutes', type=int); p.add_argument('--note', default='')
    p = sub.add_parser('uncheckin'); p.add_argument('--on', required=True); p.add_argument('--reason', required=True)
    p = sub.add_parser('reschedule'); p.add_argument('id'); p.add_argument('--date', required=True); p.add_argument('--reason', required=True)
    p = sub.add_parser('mode'); p.add_argument('--start', required=True); p.add_argument('--end', required=True); p.add_argument('--kind', choices=['night', 'low'], required=True); p.add_argument('--note', default='')
    p = sub.add_parser('clear-mode'); p.add_argument('--start', required=True); p.add_argument('--end', required=True)
    p = sub.add_parser('import-plan'); p.add_argument('--file', required=True)
    p = sub.add_parser('fault'); fs = p.add_subparsers(dest='fault_command', required=True)
    f = fs.add_parser('list'); f.add_argument('--query', default='')
    f = fs.add_parser('show'); f.add_argument('id')
    for name in ('add', 'update', 'import'):
        f = fs.add_parser(name)
        if name == 'update': f.add_argument('id')
        group = f.add_mutually_exclusive_group(required=True)
        group.add_argument('--file'); group.add_argument('--data', help='JSON 对象；复杂内容优先用本地临时文件')
    f = fs.add_parser('delete'); f.add_argument('id'); f.add_argument('--confirm', action='store_true')
    f = fs.add_parser('export-sanitized'); f.add_argument('--output', required=True); f.add_argument('--reviewed', action='store_true', help='确认理解：仅候选稿，仍须人工复核')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == 'fault':
            fault_command(root, args)
            return 0
        p, raw = get_document(root, PLAN_PATH)
        validate_plan(p)
        cmd = args.command
        if cmd == 'today':
            faults, _ = get_document(root, FAULT_PATH)
            validate_faults(faults)
            show_today(p, faults, args)
            return 0
        if cmd in ('done', 'undo'):
            selected = select_items(p, args.ids)  # all IDs checked before any write
            ds = date_used(args.on)
            before = copy.deepcopy(selected)
            for t in selected:
                if cmd == 'done' and (t['id'].startswith('song') or t['id'] in ('4-5', '8-2', '13-2', '1-7')):
                    if not any(e.startswith(('https://', 'http://')) for e in t.get('evidence', []) + args.evidence):
                        raise ValueError(f'{t["id"]} 是公开发布项，需要 --evidence 记录实际链接；未修改任何任务')
                t['done'] = cmd == 'done'
                t['completedOn'] = (t.get('completedOn') or ds) if cmd == 'done' else None
                t['note'] = merge_notes(t.get('note'), args.note)
                t['evidence'] = list(dict.fromkeys(t.get('evidence', []) + args.evidence))
            if selected == before:
                print('状态没有变化；未新增版本 / 历史。')
                return 0
            event(p, cmd, ids=list(dict.fromkeys(args.ids)), on=ds, before=before)
        elif cmd == 'note':
            target = select_items(p, [args.id])[0]
            target['note'] = merge_notes(target.get('note'), args.text)
            event(p, 'note', ids=[args.id])
        elif cmd == 'week-note':
            w = next((w for w in p['weeks'] if w['n'] == args.week), None)
            if not w: raise ValueError('周次不存在')
            w['note'] = merge_notes(w.get('note'), args.text)
            event(p, 'week-note', summary=f'W{args.week}')
        elif cmd == 'checkin':
            ds = date_used(args.on)
            if not p['meta']['day0'] <= ds <= p['meta']['end']:
                raise ValueError('打卡日期不在本计划内；计划外记录应另开日志')
            if args.minutes is not None and args.minutes < 0: raise ValueError('分钟不能为负')
            p['checkins'] = sorted(set(p['checkins']) | {ds})
            log = p.setdefault('dailyLogs', {}).setdefault(ds, {})
            log['note'] = merge_notes(log.get('note'), args.note)
            if args.minutes is not None: log['minutes'] = args.minutes
            if p == json.loads(raw):
                print('该日已打卡，且内容未变化；不重复累计。')
                return 0
            event(p, 'checkin', on=ds, summary=ds)
        elif cmd == 'uncheckin':
            ds = date_used(args.on)
            if ds not in p['checkins']:
                print('该日未打卡，无需撤销。'); return 0
            p['checkins'].remove(ds)
            log = p.setdefault('dailyLogs', {}).pop(ds, {})
            event(p, 'uncheckin', on=ds, before=log, summary=args.reason)
        elif cmd == 'reschedule':
            ds = parse_date(args.date).isoformat()
            if not p['meta']['day1'] <= ds <= p['meta']['end']:
                raise ValueError('重排须在 Day 1–98 内；扩期需显式修改整体计划')
            t = task_index(p).get(args.id)
            if not t: raise ValueError('只能重排具体任务，ID 不存在')
            if t['done']: raise ValueError('已完成任务不移动；需要更正时先明确撤销')
            before = copy.deepcopy(t)
            for day in p['dailyPlan']:
                day['actions'] = [a for a in day['actions'] if a['taskId'] != args.id]
                if day['date'] == ds:
                    day['actions'].append({'taskId': args.id, 'text': t['text']})
            t['scheduledDate'] = t['dueDate'] = ds
            t['note'] = merge_notes(t.get('note'), '重排原因：' + args.reason)
            # Wording ID stays stable even if it moves to a different week.
            for w in p['weeks']: w['tasks'] = [x for x in w['tasks'] if x['id'] != args.id]
            next(w for w in p['weeks'] if w['start'] <= ds <= w['end'])['tasks'].append(t)
            event(p, 'reschedule', ids=[args.id], before=before, summary=f'{args.id} → {ds}；{args.reason}')
        elif cmd == 'mode':
            start, end = parse_date(args.start), parse_date(args.end)
            if not p['meta']['day0'] <= start.isoformat() <= end.isoformat() <= p['meta']['end']:
                raise ValueError('豁免日期倒置或超出计划')
            obj = {'start': args.start, 'end': args.end, 'mode': args.kind, 'note': args.note}
            if obj in p.setdefault('overrides', []):
                print('同样的豁免安排已存在。'); return 0
            p['overrides'].append(obj)
            event(p, 'mode', summary=f'{args.start}—{args.end} · {args.kind}')
        elif cmd == 'clear-mode':
            parse_date(args.start); parse_date(args.end)
            before = copy.deepcopy(p.get('overrides', []))
            p['overrides'] = [x for x in before if not (x['start'] == args.start and x['end'] == args.end)]
            if before == p['overrides']:
                raise ValueError('未找到相同起止日期的模式；为避免误删未做修改')
            event(p, 'clear-mode', before=before, summary=f'{args.start}—{args.end}')
        elif cmd == 'import-plan':
            source = json.loads(Path(args.file).read_text(encoding='utf-8-sig'))
            count = import_plan_state(p, source)
            event(p, 'import-plan', summary=f'按稳定 ID 合并 {count} 项状态；保留排期、未知 ID 与已有备注')
        finish(root, PLAN_PATH, p, raw)
        if cmd in ('done', 'undo'):
            print(('已勾选：' if cmd == 'done' else '已撤销：') + ', '.join(dict.fromkeys(args.ids)))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print('操作未完成：' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
