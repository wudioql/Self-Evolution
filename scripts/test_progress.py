"""Isolated regression tests. Real user progress is never mutated."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from project_data import (ROOT, PLAN_PATH, FAULT_PATH, dump, load, tasks, task_index, calc_stats,
                          day_info, overview_md, validate_plan, validate_faults, empty_faults,
                          real_faults, sync_views, atomic_write, sanitize_faults, save_data)
from progress import import_plan_state


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='selfevo-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for rel in ('tools/90天进度表.html', 'tools/故障模式库.html', 'scripts/file-store.js', '03-90天计划.md'):
            dest = self.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text((ROOT / rel).read_text(encoding='utf-8'), encoding='utf-8')
        p = load(ROOT, PLAN_PATH)
        # Fixtures contain the schedule, not the user's actual state.
        for t in tasks(p) + p['deliverables']:
            t.update(done=False, completedOn=None, note='', evidence=[])
        for w in p['weeks']:
            w['note'] = ''
        p.update(checkins=[], dailyLogs={}, overrides=[], history=[], _orphans=[])
        p['meta']['revision'] = 1
        p['meta']['updated'] = '2026-09-06'
        # Fixtures contain the schedule, not the user's actual state:
        # reset accumulator counters too.
        for a in p.get('accumulators', []):
            if a.get('mode') == 'derived':
                continue
            a['count'] = 0
            a['lastAddedOn'] = None
            a['note'] = ''
            if a.get('mode') == 'items':
                a['items'] = []
        p['stats'] = calc_stats(p)
        for rel, obj in ((PLAN_PATH, p), (FAULT_PATH, empty_faults())):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(dump(obj), encoding='utf-8')
        sync_views(self.root)

    def p(self):
        return load(self.root, PLAN_PATH)

    def f(self):
        return load(self.root, FAULT_PATH)

    def cli(self, *args, ok=True):
        r = subprocess.run([sys.executable, str(ROOT / 'scripts/progress.py'), '--root', str(self.root), *args],
                           capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 0 if ok else 1, r.stdout + r.stderr)
        return r

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_calendar_boundaries_and_true_milestones(self):
        p = self.p()
        for ds, number, week in [('2026-09-05', -1, None), ('2026-09-06', 0, None), ('2026-09-07', 1, 1),
                                 ('2026-09-13', 7, 1), ('2026-09-14', 8, 2), ('2026-10-06', 30, 5),
                                 ('2026-11-05', 60, 9), ('2026-12-05', 90, 13), ('2026-12-13', 98, 14), ('2026-12-14', 99, None)]:
            info = day_info(p, ds)
            self.assertEqual((info['day'], info['week']), (number, week))
        self.assertEqual(len(p['dailyPlan']), 99)
        self.assertEqual([c['day'] for c in p['checkpoints']], [30, 60, 90, 98])
        validate_plan(p)

    def test_today_is_read_only(self):
        before = self.files()
        r = self.cli('today', '--date', '2026-09-06', '--json')
        info = json.loads(r.stdout)
        self.assertEqual(info['day'], 0)
        self.assertFalse(info['checkedIn'])
        self.assertEqual(before, self.files())

    def test_today_context_fields_are_derived_and_read_only(self):
        before = self.files()
        r = self.cli('today', '--date', '2026-09-07', '--json')
        info = json.loads(r.stdout)
        # Week context: fresh fixture has nothing done, so all ten W1 tasks remain.
        self.assertEqual((info['weekTitle'], info['weekDone'], info['weekTotal']),
                         ('启动与《Lemon》8 小节旋律', 0, 10))
        self.assertEqual([x['id'] for x in info['weekRemaining']],
                         ['1-0', '1-1', '1-2', '1-3', '1-4', '1-5', '1-6', '1-7', '1-8', '1-9'])
        self.assertIn({'id': '1-9', 'due': '2026-09-12', 'optional': True}, info['weekRemaining'])
        # Tomorrow preview comes from the next dailyPlan entry, not from new data.
        self.assertEqual(info['tomorrowDate'], '2026-09-08')
        self.assertEqual(info['tomorrow']['taskId'], '1-2')
        # Milestones: nearest two of the existing checkpoints and deliverables.
        self.assertEqual([(m['date'], m['label']) for m in info['nextMilestones']],
                         [('2026-10-04', '歌 #1《Lemon》截止'), ('2026-10-06', 'Day 30 复检')])
        self.assertEqual(before, self.files())
        # Completing a task shrinks the derived week context; still no extra writes.
        self.cli('done', '1-0', '--on', '2026-09-07', '--note', '本人确认')
        info = json.loads(self.cli('today', '--date', '2026-09-07', '--json').stdout)
        self.assertNotIn('1-0', [x['id'] for x in info['weekRemaining']])
        self.assertEqual(info['weekDone'], 1)

    def test_today_text_shows_week_milestone_tomorrow_lines(self):
        r = self.cli('today', '--date', '2026-09-07')
        self.assertIn('本周：W1 · 启动与《Lemon》8 小节旋律 · 0/10；剩余：', r.stdout)
        self.assertIn('下一里程碑：2026-10-04 歌 #1《Lemon》截止 · 2026-10-06 Day 30 复检', r.stdout)
        self.assertIn('明日：[1-2]', r.stdout)
        # Day 0 has no week number; the week line must not appear there.
        self.assertNotIn('本周：', self.cli('today', '--date', '2026-09-06').stdout)

    def accumulator(self, p, aid):
        return next(a for a in p['accumulators'] if a['id'] == aid)

    def test_accumulator_status_in_today_and_read_only(self):
        before = self.files()
        info = json.loads(self.cli('today', '--date', '2026-09-10', '--json').stdout)
        rows = {x['id']: x for x in info['accumulators']}
        self.assertEqual(set(rows), {'taste', 'terms', 'lib'})
        self.assertEqual(rows['taste']['label'], '好听元素清单 0/30（下一档 3·2026-11-02）')
        self.assertEqual(rows['terms']['label'], '英语术语表 0/80（下一档 10·2026-09-19）')
        self.assertEqual(rows['lib']['label'], '故障模式库 0/30（下一档 5·2026-09-13）')
        self.assertIn('故障模式库', info['accumNudge'])
        self.assertIn('积累：好听元素清单 0/30', self.cli('today', '--date', '2026-09-10').stdout)
        # Day 0 shows no accumulator line (collection starts W1).
        self.assertNotIn('积累：', self.cli('today', '--date', '2026-09-06').stdout)
        self.assertEqual(before, self.files())

    def test_accumulate_items_appends_syncs_and_idempotent(self):
        rev = self.p()['meta']['revision']
        text = '[Lemon] 1:23 鼓停了半拍才进副歌'
        self.cli('accumulate', 'taste', '--text', text, '--on', '2026-09-10')
        p = self.p()
        a = self.accumulator(p, 'taste')
        self.assertEqual(a['count'], 1)
        self.assertEqual(a['items'], [{'on': '2026-09-10', 'text': text}])
        self.assertEqual(a['lastAddedOn'], '2026-09-10')
        self.assertEqual(p['meta']['revision'], rev + 1)
        self.assertIn(text, (self.root / 'progress/进度总览.md').read_text(encoding='utf-8'))
        self.assertEqual(sync_views(self.root, check=True), [])
        # Same entry again: no new revision, no duplicate item.
        r2 = self.cli('accumulate', 'taste', '--text', text, '--on', '2026-09-10')
        self.assertIn('已记录过', r2.stdout)
        p2 = self.p()
        self.assertEqual(p2['meta']['revision'], rev + 1)
        self.assertEqual(len(self.accumulator(p2, 'taste')['items']), 1)
        # A different entry grows the count; reaching the 3-item checkpoint
        # moves the next step to the overall target.
        self.cli('accumulate', 'taste', '--text', '[Lemon] 2:10 弦乐进前的留白', '--on', '2026-09-10')
        out = self.cli('accumulate', 'taste', '--text', '第三条', '--on', '2026-09-10').stdout
        self.assertEqual(self.accumulator(self.p(), 'taste')['count'], 3)
        self.assertIn('积累已更新：好听元素清单 3/30', out)
        self.assertIn('下一档 30 条 · 2026-12-05', out)

    def test_accumulate_reported_grows_and_rejects_downgrade(self):
        self.cli('accumulate', 'terms', '--set', '10', '--note', 'Service Manual Ch.1 读完', '--on', '2026-09-10')
        a = self.accumulator(self.p(), 'terms')
        self.assertEqual((a['count'], a['lastAddedOn']), (10, '2026-09-10'))
        self.assertIn('Service Manual Ch.1 读完', a['note'])
        self.assertIn('英语术语表 10/80（下一档 25·2026-09-26）', self.cli('today', '--date', '2026-09-10').stdout)
        r = self.cli('accumulate', 'terms', '--set', '5', '--on', '2026-09-10', ok=False)
        self.assertIn('只允许增长', r.stderr)
        self.assertEqual(self.accumulator(self.p(), 'terms')['count'], 10)
        self.cli('accumulate', 'terms', '--set', '5', '--on', '2026-09-10', '--force')
        self.assertEqual(self.accumulator(self.p(), 'terms')['count'], 5)
        self.assertIn('累计数已是 5', self.cli('accumulate', 'terms', '--set', '5', '--on', '2026-09-10').stdout)

    def test_accumulate_derived_and_future_rejected(self):
        r = self.cli('accumulate', 'lib', '--text', '不该手设', '--on', '2026-09-10', ok=False)
        self.assertIn('fault add', r.stderr)
        # The derived count follows real fault records only.
        self.cli('fault', 'add', '--data', json.dumps({'symptom': '测试故障现象'}, ensure_ascii=False))
        self.assertIn('故障模式库 1/30', self.cli('today', '--date', '2026-09-10').stdout)
        r2 = self.cli('accumulate', 'taste', '--text', '未来条目', '--on', '2027-01-15', ok=False)
        self.assertIn('未来', r2.stderr)
        self.assertEqual(self.accumulator(self.p(), 'taste')['count'], 0)

    def test_accumulator_nudges_stale_and_near_milestone(self):
        # Nothing recorded yet: day 1 has no nudge at all.
        self.assertNotIn('没新增', self.cli('today', '--date', '2026-09-08').stdout)
        # Two idle days: staleness fires; taste and lib tie, list order wins.
        self.assertIn('好听元素清单：已 2 天没新增', self.cli('today', '--date', '2026-09-09').stdout)
        # Milestone proximity (lib due 2026-09-13) outranks staleness.
        out = self.cli('today', '--date', '2026-09-12').stdout
        self.assertIn('故障模式库：距下一档（5 条 · 2026-09-13）还剩 1 天', out)
        self.assertNotIn('好听元素清单：', out)
        # A recorded entry resets its staleness window.
        self.cli('accumulate', 'taste', '--text', '[Lemon] 1:23 鼓停了半拍才进副歌', '--on', '2026-09-09')
        self.assertNotIn('没新增', self.cli('today', '--date', '2026-09-10').stdout)

    def test_night_mode_suppresses_accumulator_lines(self):
        self.cli('mode', '--start', '2026-09-10', '--end', '2026-09-10', '--kind', 'night')
        out = self.cli('today', '--date', '2026-09-10').stdout
        self.assertNotIn('积累：', out)
        self.assertNotIn('没新增', out)
        self.assertNotIn('距下一档', out)
        # Low-energy day keeps the status line (顺带, 不加量).
        self.assertIn('积累：', self.cli('today', '--date', '2026-09-10', '--mode', 'low').stdout)

    def test_public_overview_deterministic_without_private_fault_file(self):
        # progress/进度总览.md is public and committed; CI never has
        # data/faults.local.json, so the view must be derivable from
        # plan90.json alone and `sync-plan.py --check` must pass there.
        p = self.p()
        rendered = (self.root / 'progress/进度总览.md').read_text(encoding='utf-8')
        self.assertEqual(rendered, overview_md(p))
        (self.root / FAULT_PATH).unlink()
        self.assertEqual(sync_views(self.root, check=True), [])
        self.assertEqual((self.root / 'progress/进度总览.md').read_text(encoding='utf-8'), overview_md(p))
        self.assertIn('| **故障模式库** | — |', rendered)

    def test_import_plan_merges_accumulators(self):
        p = self.p()
        payload = copy.deepcopy(p)
        taste = self.accumulator(payload, 'taste')
        taste['items'] = [{'on': '2026-09-08', 'text': '来自备份的一条'}]
        taste['count'] = 1
        taste['lastAddedOn'] = '2026-09-08'
        self.accumulator(payload, 'terms')['count'] = 5
        payload['accumulators'].append({'id': 'mystery', 'text': 'x', 'unit': '个', 'target': 1,
                                        'mode': 'reported', 'count': 1, 'lastAddedOn': None})
        path = self.root / 'backup.local.json'
        path.write_text(dump(payload), encoding='utf-8')
        self.cli('import-plan', '--file', str(path))
        p2 = self.p()
        self.assertEqual(self.accumulator(p2, 'taste')['count'], 1)
        self.assertEqual(self.accumulator(p2, 'terms')['count'], 5)
        self.assertNotIn('mystery', [a['id'] for a in p2['accumulators']])
        self.assertTrue(any(o.get('kind') == 'accumulator' and o.get('id') == 'mystery' for o in p2['_orphans']))
        # Newer master entries never lose to an older backup.
        self.cli('accumulate', 'taste', '--text', '正本新条目', '--on', '2026-09-09')
        self.cli('import-plan', '--file', str(path))
        a2 = self.accumulator(self.p(), 'taste')
        self.assertEqual(a2['count'], 2)
        self.assertEqual(a2['items'], [{'on': '2026-09-08', 'text': '来自备份的一条'},
                                       {'on': '2026-09-09', 'text': '正本新条目'}])
        self.assertEqual(self.accumulator(self.p(), 'terms')['count'], 5)

    def test_done_persists_and_generates_matching_views(self):
        self.cli('done', '1-0', '--on', '2026-09-06', '--note', '本人确认已响')
        p = self.p()
        self.assertTrue(task_index(p)['1-0']['done'])
        self.assertEqual(p['stats']['doneTasks'], 1)
        self.assertEqual(task_index(p)['1-0']['completedOn'], '2026-09-06')
        self.assertEqual(p['checkins'], [])
        self.assertIn('- [x] **`1-0`**', (self.root / 'progress/进度总览.md').read_text(encoding='utf-8'))
        self.assertEqual(sync_views(self.root, check=True), [])
        # A fresh process sees file state, not Python / chat memory.
        r = self.cli('today', '--date', '2026-09-06', '--json')
        self.assertNotIn('1-0', [a['taskId'] for a in json.loads(r.stdout)['actions']])

    def test_done_is_idempotent(self):
        args = ('done', '1-0', '--on', '2026-09-06', '--note', '已响')
        self.cli(*args)
        before = self.files()
        self.cli(*args)
        self.assertEqual(before, self.files())

    def test_unknown_batch_id_does_not_partly_write(self):
        before = self.files()
        self.cli('done', '1-0', 'no-such-id', '--on', '2026-09-06', ok=False)
        self.assertEqual(before, self.files())

    def test_publication_requires_link_and_no_partial_batch(self):
        before = self.files()
        self.cli('done', '1-0', '4-5', '--on', '2026-09-06', ok=False)
        self.assertEqual(before, self.files())
        self.cli('done', '4-5', 'song1', '--on', '2026-09-06', '--evidence', 'https://example.invalid/user-confirmed')
        self.assertTrue(task_index(self.p())['4-5']['done'])
        self.assertEqual(self.p()['stats']['delivDone'], 1)

    def test_undo_keeps_evidence_notes_and_history(self):
        self.cli('done', '1-0', '--on', '2026-09-06', '--note', '第一次记录', '--evidence', 'local-output')
        self.cli('undo', '1-0', '--on', '2026-09-06', '--note', '更正')
        t = task_index(self.p())['1-0']
        self.assertFalse(t['done'])
        self.assertIsNone(t['completedOn'])
        self.assertEqual(t['evidence'], ['local-output'])
        self.assertIn('第一次记录', t['note'])
        self.assertEqual([x['action'] for x in self.p()['history']], ['done', 'undo'])
        self.assertEqual(len(list((self.root / 'progress/.backups').glob('*.json'))), 2)

    def test_partial_note_does_not_complete_task(self):
        self.cli('note', '1-2', '--text', '前四小节，未导出')
        self.assertFalse(task_index(self.p())['1-2']['done'])
        self.assertEqual(self.p()['stats']['doneTasks'], 0)
        self.cli('week-note', '1', '--text', '三行回顾')
        self.assertIn('三行回顾', self.p()['weeks'][0]['note'])

    def test_checkin_idempotence_and_correction(self):
        args = ('checkin', '--on', '2026-09-06', '--minutes', '25', '--note', '实际做过')
        self.cli(*args)
        before = self.files()
        self.cli(*args)
        self.assertEqual(before, self.files())
        self.assertEqual(self.p()['checkins'], ['2026-09-06'])
        self.assertEqual(self.p()['stats']['doneTasks'], 0)
        self.cli('uncheckin', '--on', '2026-09-06', '--reason', '误记')
        self.assertEqual(self.p()['checkins'], [])

    def test_reschedule_keeps_stable_id_state_and_count(self):
        p = self.p()
        self.cli('note', '1-3', '--text', '已看一半')
        self.cli('reschedule', '1-3', '--date', '2026-09-14', '--reason', '本人确认')
        newer = self.p()
        t = task_index(newer)['1-3']
        self.assertIn(t, newer['weeks'][1]['tasks'])
        self.assertNotIn('1-3', [x['id'] for x in newer['weeks'][0]['tasks']])
        self.assertEqual(t['dueDate'], '2026-09-14')
        self.assertIn('已看一半', t['note'])
        self.assertEqual(set(task_index(p)), set(task_index(newer)))
        validate_plan(newer)

    def test_night_override_and_low_mode_do_not_fake_completion(self):
        self.cli('mode', '--start', '2026-10-05', '--end', '2026-10-10', '--kind', 'night')
        p = self.p()
        self.assertEqual(p['stats']['doneTasks'], 0)
        info = day_info(p, '2026-10-06')
        self.assertEqual(info['actions'], [])
        self.assertEqual(info['budgetMinutes'], 10)
        self.assertLessEqual(len(day_info(p, '2026-09-07', 'low')['actions']), 1)
        self.cli('clear-mode', '--start', '2026-10-05', '--end', '2026-10-10')
        self.assertEqual(self.p()['overrides'], [])

    def test_sync_never_overwrites_state_unknown_fields_or_orphans(self):
        p = self.p()
        p['meta']['futureField'] = {'a': 42}
        p['_orphans'] = [{'id': 'old-task', 'note': '保留'}]
        task_index(p)['1-2']['futureTaskField'] = '保留'
        (self.root / PLAN_PATH).write_text(dump(p), encoding='utf-8')
        sync_views(self.root)
        before = self.files()
        self.assertEqual(sync_views(self.root, check=True), [])
        self.assertEqual(sync_views(self.root), [])
        self.assertEqual(before, self.files())
        self.assertEqual(self.p()['meta']['futureField'], {'a': 42})

    def test_fault_record_unknowns_and_patch_persistence(self):
        self.cli('fault', 'add', '--data', json.dumps({'symptom': '测试现象', 'unknownExtension': {'value': '保留'}}, ensure_ascii=False))
        record = self.f()['items'][0]
        self.assertEqual(record['id'], 'FM-0001')
        self.assertIsNone(record['isRecurring'])
        self.assertIsNone(record['isSolved'])
        self.assertIsNone(record['downtimeMin'])
        self.assertEqual(record['date'], '')
        self.cli('fault', 'update', 'FM-0001', '--data', '{"rootCause":"仍待确认","downtimeMin":0,"isSolved":false}')
        self.assertEqual(self.f()['items'][0]['unknownExtension'], {'value': '保留'})
        self.assertEqual(self.p()['stats']['doneTasks'], 0)
        self.assertIn('测试现象', (self.root / 'data/故障模式库.local.md').read_text(encoding='utf-8'))
        self.assertEqual(sync_views(self.root, check=True), [])

    def test_fault_delete_requires_explicit_flag_and_works(self):
        self.cli('fault', 'add', '--data', '{"symptom":"测试删除"}')
        before = self.files()
        self.cli('fault', 'delete', 'FM-0001', ok=False)
        self.assertEqual(before, self.files())
        self.cli('fault', 'delete', 'FM-0001', '--confirm')
        self.assertEqual(self.f()['items'], [])
        self.assertEqual(self.f()['history'][-1]['before']['symptom'], '测试删除')

    def test_invalid_fault_inputs_do_not_touch_file(self):
        for data in ('{"symptom":"测试","downtimeMin":-1}', '{"symptom":"测试","isSolved":"false"}',
                     '{"symptom":"测试","date":"2026-02-30"}', '{}'):
            before = self.files()
            self.cli('fault', 'add', '--data', data, ok=False)
            self.assertEqual(before, self.files())

    def test_legacy_progress_keeps_week_task_notes_and_unknown_ids(self):
        p = self.p()
        task_index(p)['1-0']['done'] = True
        p['stats'] = calc_stats(p)  # fixture represents a valid current master
        payload = {'done': {'1-0': False, '1-2': True, 'removed-1': True},
                   'notes': {'1': '旧周备注', '1-2': '旧任务备注'}, 'deliv': {}, 'checkins': ['2026-09-06']}
        import_plan_state(p, payload)
        self.assertTrue(task_index(p)['1-0']['done'])
        self.assertTrue(task_index(p)['1-2']['done'])
        self.assertEqual(p['weeks'][0]['note'], '旧周备注')
        self.assertEqual(task_index(p)['1-2']['note'], '旧任务备注')
        self.assertEqual(p['_orphans'][0]['id'], 'removed-1')
        self.assertEqual(p['checkins'], ['2026-09-06'])
        p['stats'] = calc_stats(p)
        validate_plan(p)

    def test_legacy_faults_samples_excluded_and_conflicts_rejected(self):
        payload = {'items': [{'id': 'sample1', 'symptom': '【示例】测试'}, {'id': 'old-real', 'symptom': '真实测试记录'}]}
        self.cli('fault', 'import', '--data', json.dumps(payload))
        self.assertEqual(len(real_faults(self.f())), 1)
        self.cli('fault', 'import', '--data', json.dumps(payload))
        self.assertEqual(len(self.f()['items']), 2)  # repeat import never duplicates the legacy sample
        before = self.files()
        conflict = {'items': [{'id': 'new-one', 'symptom': '不能部分写入'}, {'id': 'old-real', 'symptom': '冲突内容'}]}
        self.cli('fault', 'import', '--data', json.dumps(conflict), ok=False)
        self.assertEqual(before, self.files())

    def test_sanitization_allowlist_removes_private_metadata_and_text(self):
        d = empty_faults()
        d['config']['sensitive'] = ['RECIPE_SECRET']
        d['items'] = [{'id': 'ID_SECRET', 'symptom': 'MODEL_SECRET RECIPE_SECRET', 'eqType': 'MODEL_SECRET',
                       'eqModel': 'MODEL_SECRET', 'eqId': 'ID_SECRET', 'alarmCode': 'ALARM_SECRET', 'condition': 'COND_SECRET',
                       'links': '/secret/path', 'date': '2026-09-06', 'createdAt': '2026-09-06T08:21:11Z',
                       'unknown': 'KEEP_PRIVATE', 'notes': 'ALARM_SECRET /secret/path'}]
        d['history'] = [{'secret': 'KEEP_PRIVATE'}]
        result = sanitize_faults(d)
        encoded = dump(result)
        for word in ('MODEL_SECRET', 'RECIPE_SECRET', 'ID_SECRET', 'ALARM_SECRET', 'COND_SECRET', '/secret/path', 'KEEP_PRIVATE', '08:21:11'):
            self.assertNotIn(word, encoded)
        self.assertEqual(result['items'][0]['date'], '2026-09')
        self.assertNotIn('config', result)
        self.assertNotIn('history', result)

    def test_private_html_never_contaminates_public_shell(self):
        secret = 'SYNTHETIC_PRIVATE_TOKEN'
        self.cli('fault', 'add', '--data', json.dumps({'symptom': secret}))
        for name in ('tools/故障模式库.html', 'tools/90天进度表.html', 'progress/进度总览.md', PLAN_PATH):
            self.assertNotIn(secret, (self.root / name).read_text(encoding='utf-8'))
        self.assertIn(secret, (self.root / 'tools/故障模式库.local.html').read_text(encoding='utf-8'))

    def test_embedded_user_text_cannot_close_script_tag(self):
        payload = {'symptom': '</script><script>alert("NO")</script>'}
        self.cli('fault', 'add', '--data', json.dumps(payload))
        html = (self.root / 'tools/故障模式库.local.html').read_text(encoding='utf-8')
        self.assertNotIn(payload['symptom'], html)
        self.assertIn('\\u003c/script\\u003e', html)
        import re
        obj = json.loads(re.search(r'<script type="application/json" id="project-data">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(obj['items'][0]['symptom'], payload['symptom'])

    def test_atomic_write_rejects_stale_read_and_preserves_newer_value(self):
        path = self.root / 'test.json'
        atomic_write(path, 'first')
        raw = path.read_text(encoding='utf-8')
        atomic_write(path, 'newer')
        with self.assertRaises(ValueError):
            atomic_write(path, 'stale overwrite', expected=raw, backup=True)
        self.assertEqual(path.read_text(encoding='utf-8'), 'newer')
        self.assertFalse(path.with_name('test.json.lock').exists())

    def test_lock_conflict_does_not_delete_other_writers_lock(self):
        path = self.root / 'test.json'
        lock = self.root / 'test.json.lock'
        lock.write_text('other writer', encoding='utf-8')
        with self.assertRaises(ValueError):
            atomic_write(path, 'bad')
        self.assertTrue(lock.exists())
        self.assertFalse(path.exists())

    def test_known_private_value_is_rejected_from_public_progress(self):
        (self.root / '01-个人档案.local.md').write_text('| 公开 | 真值（本地） |\n|---|---|\n| 代称 | SYNTHETIC_SECRET |\n', encoding='utf-8')
        before = self.files()
        self.cli('note', '1-2', '--text', 'SYNTHETIC_SECRET', ok=False)
        self.assertEqual(before, self.files())

    def test_broken_json_is_not_silently_reset(self):
        path = self.root / FAULT_PATH
        path.write_text('{ broken file', encoding='utf-8')
        before = self.files()
        self.cli('fault', 'add', '--data', '{"symptom":"not written"}', ok=False)
        self.assertEqual(before, self.files())

    def test_validate_boolean_string_duplicate_id_and_stats(self):
        p = self.p()
        task_index(p)['1-0']['done'] = 'false'
        with self.assertRaises(ValueError):
            validate_plan(p)
        p = self.p()
        p['weeks'][0]['tasks'][1]['id'] = p['weeks'][0]['tasks'][0]['id']
        with self.assertRaises(ValueError):
            validate_plan(p)
        p = self.p()
        p['stats']['doneTasks'] = 99
        with self.assertRaises(ValueError):
            validate_plan(p)


    def test_b1_missing_duplicate_reversed_markers_reject_without_writes(self):
        from project_data import replace_block
        target = self.root / '03-90天计划.md'
        original = target.read_text(encoding='utf-8')
        begin, end = '<!-- PLAN-SCHEDULE:BEGIN -->', '<!-- PLAN-SCHEDULE:END -->'
        corruptions = [original.replace(begin, ''), original.replace(end, ''),
                       original.replace(begin, begin + begin), original.replace(end, end + end),
                       original.replace(begin, 'SWAP').replace(end, begin).replace('SWAP', end)]
        for corrupted in corruptions:
            target.write_text(corrupted, encoding='utf-8')
            before = self.files()
            for check in (True, False):
                with self.subTest(check=check, markers=corruptions.index(corrupted)):
                    with self.assertRaises(ValueError):
                        sync_views(self.root, check=check)
                    self.assertEqual(before, self.files())
        with self.assertRaises(ValueError):
            replace_block('END before START', 'START', 'END', 'content')

    def test_b1_missing_execution_template_is_not_silently_skipped(self):
        (self.root / '03-90天计划.md').unlink()
        before = self.files()
        with self.assertRaises((ValueError, OSError)):
            sync_views(self.root, check=True)
        self.assertEqual(before, self.files())

    def test_b1_cli_reports_saved_json_separately_from_failed_views(self):
        target = self.root / '03-90天计划.md'
        target.write_text(target.read_text(encoding='utf-8').replace('<!-- PLAN-SCHEDULE:END -->', ''))
        r = self.cli('done', '1-0', '--on', '2026-09-06', ok=False)
        self.assertIn('JSON 已保存', r.stderr)
        self.assertTrue(task_index(self.p())['1-0']['done'])
        self.assertNotIn('只读视图已同步', r.stdout)

    def test_b2_bad_import_dates_abort_entire_file_operation(self):
        future = '2099-01-01'
        valid = {'done': {'1-0': True}, 'notes': {'1-2': 'keep original'}, 'checkins': []}
        cases = [dict(valid, checkins=[future]), dict(valid, checkins=['2026-09-05']),
                 dict(valid, dailyLogs={future: {'note': 'not yet done'}})]
        v2 = self.p()
        task_index(v2)['1-0'].update(done=True, completedOn=future)
        v2['stats'] = calc_stats(v2)
        cases.append(v2)
        for payload in cases:
            file = self.root / 'incoming.local.json'
            file.write_text(dump(payload), encoding='utf-8')
            before = self.files()
            self.cli('import-plan', '--file', str(file), ok=False)
            self.assertEqual(before, self.files())

    def test_b2_invalid_import_does_not_partly_mutate_in_memory(self):
        p = self.p()
        before = copy.deepcopy(p)
        with self.assertRaises(ValueError):
            import_plan_state(p, {'done': {'1-0': True}, 'checkins': ['not-a-date']})
        self.assertEqual(p, before)

    def test_b2_invalid_source_date_cannot_hide_behind_existing_completion(self):
        p = self.p()
        task_index(p)['1-0'].update(done=True, completedOn='2026-09-06')
        p['stats'] = calc_stats(p)
        source = copy.deepcopy(p)
        task_index(source)['1-0']['completedOn'] = '2099-01-01'
        before = copy.deepcopy(p)
        with self.assertRaises(ValueError):
            import_plan_state(p, source)
        self.assertEqual(p, before)

    def test_b2_invalid_unknown_record_is_not_silently_quarantined(self):
        p = self.p()
        source = {'schema': 'self-evolution/plan90/v1', 'weeks': [
            {'n': 1, 'tasks': [{'id': 'removed-42', 'done': True, 'completedOn': '2099-01-01'}]}]}
        before = copy.deepcopy(p)
        with self.assertRaises(ValueError):
            import_plan_state(p, source)
        self.assertEqual(p, before)

    def test_b3_expected_absence_is_distinct_from_unchecked_write(self):
        path = self.root / 'created.json'
        atomic_write(path, 'first writer', expected=None)
        before = self.files()
        with self.assertRaises(ValueError):
            atomic_write(path, 'second writer', expected=None, backup=True)
        self.assertEqual(self.files(), before)
        atomic_write(path, 'intentional generated replacement')
        self.assertEqual(path.read_text(encoding='utf-8'), 'intentional generated replacement')

    def test_b3_two_initializers_cannot_overwrite_new_fault_library(self):
        import contextlib
        import io
        from progress import get_document, finish
        from project_data import normalize_fault_record
        (self.root / FAULT_PATH).unlink()
        a, raw_a = get_document(self.root, FAULT_PATH)
        b, raw_b = get_document(self.root, FAULT_PATH)
        self.assertIsNone(raw_a)
        self.assertIsNone(raw_b)
        a['items'] = [normalize_fault_record({'symptom': 'synthetic first'}, 'FM-0001', '2026-09-06')]
        b['items'] = [normalize_fault_record({'symptom': 'synthetic second'}, 'FM-0001', '2026-09-06')]
        with contextlib.redirect_stdout(io.StringIO()):
            finish(self.root, FAULT_PATH, a, raw_a)
            before = self.files()
            with self.assertRaises(ValueError):
                finish(self.root, FAULT_PATH, b, raw_b)
        self.assertEqual(before, self.files())

    def test_b3_simultaneous_first_writes_allow_exactly_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier = Barrier(2)
        path = self.root / 'simultaneous.json'
        def write(text):
            barrier.wait()
            try:
                atomic_write(path, text, expected=None, backup=True)
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(write, 'A')
            b = pool.submit(write, 'B')
            self.assertEqual(sum([a.result(), b.result()]), 1)
        self.assertIn(path.read_text(encoding='utf-8'), ('A', 'B'))
        self.assertFalse(path.with_name(path.name + '.lock').exists())

    def test_b5_notes_only_and_week_notes_are_additive_and_repeatable(self):
        p = self.p()
        p['weeks'][0]['note'] = 'newer week note'
        task_index(p)['1-2']['note'] = 'newer task note'
        payload = {'done': {}, 'notes': {'1': 'old week\nsecond line', '1-2': 'old task\nsecond line',
                                        'removed-7': 'orphan note'}, 'deliv': {}, 'checkins': []}
        import_plan_state(p, payload)
        self.assertIn('newer task note', task_index(p)['1-2']['note'])
        self.assertIn('old task\nsecond line', task_index(p)['1-2']['note'])
        self.assertIn('newer week note', p['weeks'][0]['note'])
        self.assertIn('old week\nsecond line', p['weeks'][0]['note'])
        self.assertEqual(p['_orphans'][0]['note'], 'orphan note')
        after = copy.deepcopy(p)
        import_plan_state(p, payload)
        self.assertEqual(p, after)

    def test_b6_release_and_delivery_gate_ipa_but_equipment_does_not(self):
        p = self.p()
        for t in tasks(p):
            if t['track'] == 'sound':
                t['done'] = True
        p['stats'] = calc_stats(p)
        ds = '2026-10-16'
        before = copy.deepcopy(p)
        self.assertNotIn('6-5', [a['taskId'] for a in day_info(p, ds)['actions']])
        self.assertEqual(before, p)
        task_index(p)['4-5']['done'] = True
        # Publication checkbox alone is not the full delivery's four-part acceptance.
        self.assertNotIn('6-5', [a['taskId'] for a in day_info(p, ds)['actions']])
        next(d for d in p['deliverables'] if d['id'] == 'song1')['done'] = True
        self.assertIn('6-5', [a['taskId'] for a in day_info(p, ds)['actions']])
        for mode in ('low', 'night'):
            self.assertNotIn('6-5', [a['taskId'] for a in day_info(p, ds, mode)['actions']])

    def test_b6_music_due_today_is_not_yet_overdue(self):
        p = self.p()
        for t in tasks(p):
            if t['track'] == 'sound':
                t['done'] = True
        task_index(p)['4-5']['dueDate'] = '2026-10-16'
        next(d for d in p['deliverables'] if d['id'] == 'song1')['dueDate'] = '2026-10-16'
        self.assertIn('6-5', [a['taskId'] for a in day_info(p, '2026-10-16')['actions']])



    def test_b4_python_and_javascript_share_validation_contract_cases(self):
        fixtures = []
        missing = object()
        def case(name, changes=(), expected=False, kind='plan', as_of='2026-09-06'):
            value = self.p() if kind == 'plan' else empty_faults()
            for path, replacement in changes:
                obj = value
                for key in path[:-1]:
                    obj = obj[key]
                if replacement is missing:
                    del obj[path[-1]]
                else:
                    obj[path[-1]] = replacement
            if kind == 'plan' and name not in ('stats-bool', 'stats-extra', 'invalid-state-boolean'):
                value['stats'] = calc_stats(value)
            fixtures.append({'name': name, 'kind': kind, 'data': value, 'expected': expected, 'asOf': as_of})
        t = ['weeks', 0, 'tasks', 0]
        case('clean', expected=True)
        case('unknown-fields', [(['extension'], {'keep': ['yes']})], True)
        case('integer-json-number', [(['meta', 'revision'], 1.0)], True)
        case('unknown-completion-date', [(t+['done'], True)], True)
        case('early-actual-completion', [(t+['done'], True), (t+['completedOn'], '2026-09-05')], True)
        case('late-actual-completion', [(t+['done'], True), (t+['completedOn'], '2026-12-15')], True, as_of='2026-12-20')
        case('before-day0', [(t+['scheduledDate'], '2026-09-05')])
        case('after-end', [(t+['dueDate'], '2026-12-14')])
        case('inverted-dates', [(t+['scheduledDate'], '2026-09-08')])
        case('invalid-date', [(t+['scheduledDate'], '2026-02-30')])
        case('missing-track', [(t+['track'], missing)])
        case('prototype-track', [(t+['track'], 'toString')])
        case('null-note', [(t+['note'], None)])
        case('numeric-note', [(t+['note'], 0)])
        case('null-evidence', [(t+['evidence'], None)])
        case('non-string-evidence', [(t+['evidence'], [False])])
        case('numeric-completion', [(t+['completedOn'], 0)])
        case('false-completion', [(t+['completedOn'], False)])
        case('incomplete-with-date', [(t+['completedOn'], '2026-09-06')])
        case('future-completion', [(t+['done'], True), (t+['completedOn'], '2026-09-07')])
        case('invalid-state-boolean', [(t+['done'], 'false')])
        case('id-newline', [(t+['id'], '1-0\n')])
        case('duplicate-id', [(['weeks', 0, 'tasks', 1, 'id'], '1-0')])
        case('bad-optional', [(t+['optional'], 'false')])
        case('null-dependencies', [(t+['dependsOn'], None)])
        case('missing-dependency', [(t+['dependsOn'], ['not-a-task'])])
        case('revision-bool', [(['meta', 'revision'], True)])
        case('revision-fraction', [(['meta', 'revision'], 1.5)])
        case('revision-unsafe', [(['meta', 'revision'], 2**53)])
        case('missing-updated', [(['meta', 'updated'], missing)])
        case('day98-drift', [(['meta', 'day98'], '2026-12-14')])
        case('week-number-bool', [(['weeks', 0, 'n'], True)])
        case('null-week-note', [(['weeks', 0, 'note'], None)])
        case('daily-number-bool', [(['dailyPlan', 0, 'day'], False)])
        case('daily-fraction-budget', [(['dailyPlan', 0, 'budgetMinutes'], 2.5)])
        case('missing-action-id', [(['dailyPlan', 0, 'actions', 0, 'taskId'], 'absent')])
        case('checkpoint-number-bool', [(['checkpoints', 0, 'day'], True)])
        case('future-checkin', [(['checkins'], ['2026-09-07'])])
        case('before-plan-checkin', [(['checkins'], ['2026-09-05'])])
        case('duplicate-checkin', [(['checkins'], ['2026-09-06', '2026-09-06'])])
        case('good-checkin', [(['checkins'], ['2026-09-06'])], True)
        case('good-daily-log', [(['dailyLogs'], {'2026-09-06': {'note': '', 'minutes': 0}})], True)
        case('future-daily-log', [(['dailyLogs'], {'2026-09-07': {'note': ''}})])
        case('null-daily-log', [(['dailyLogs'], {'2026-09-06': None})])
        case('null-log-minutes', [(['dailyLogs'], {'2026-09-06': {'minutes': None}})])
        case('fraction-log-minutes', [(['dailyLogs'], {'2026-09-06': {'minutes': 2.5}})])
        case('out-of-range-override', [(['overrides'], [{'start': '2026-09-05', 'end': '2026-09-06', 'mode': 'low'}])])
        case('future-override-is-a-plan', [(['overrides'], [{'start': '2026-09-07', 'end': '2026-09-10', 'mode': 'night'}])], True)
        case('stats-bool', [(['stats', 'doneTasks'], False)])
        case('stats-extra', [(['stats', 'extra'], 1)])
        case('null-history', [(['history'], None)])
        case('null-orphans', [(['_orphans'], None)])
        def acc_doc(mode='items', count=1, on='2026-09-06', cp=('9-0',), last='2026-09-06'):
            a = {'id': 'taste', 'text': '好听元素清单', 'unit': '条', 'target': 30, 'mode': mode,
                 'checkpoints': [{'count': 3, 'taskId': t} for t in cp]}
            if mode != 'derived':
                a['count'] = count
                a['lastAddedOn'] = last
                if mode == 'items':
                    a['items'] = [{'on': on, 'text': 'x'}]
            return a
        case('acc-clean', [(['accumulators'], [acc_doc()])], True)
        case('acc-count-mismatch', [(['accumulators'], [acc_doc(count=2)])])
        case('acc-future-item', [(['accumulators'], [acc_doc(on='2026-09-07')])])
        case('acc-bad-mode', [(['accumulators'], [acc_doc(mode='itemsX')])])
        case('acc-unknown-checkpoint', [(['accumulators'], [acc_doc(cp=('99-9',))])])
        case('acc-derived-minimal', [(['accumulators'], [acc_doc(mode='derived')])], True)
        case('acc-negative-count', [(['accumulators'], [acc_doc(mode='reported', count=-1)])])
        case('fault-clean', expected=True, kind='fault')
        case('fault-negative-revision', [(['meta', 'revision'], -1)], kind='fault')
        case('fault-boolean-revision', [(['meta', 'revision'], True)], kind='fault')
        case('fault-zero-next-id', [(['meta', 'nextId'], 0)], kind='fault')
        case('fault-integer-next-id', [(['meta', 'nextId'], 1.0)], True, kind='fault')
        for name, item, expected in [
            ('minimal', {'id': 'FM-0001', 'symptom': 'synthetic'}, True),
            ('unknowns', {'id': 'x', 'date': '', 'isSolved': None, 'downtimeMin': None}, True),
            ('month', {'id': 'x', 'date': '2026-09'}, True),
            ('bad-month', {'id': 'x', 'date': '2026-13'}, False),
            ('year-zero', {'id': 'x', 'date': '0000-01-01'}, False),
            ('null-text', {'id': 'x', 'notes': None}, False),
            ('bad-boolean', {'id': 'x', 'isSample': 'false'}, False),
            ('negative-minutes', {'id': 'x', 'downtimeMin': -1}, False),
            ('boolean-minutes', {'id': 'x', 'downtimeMin': True}, False),
            ('id-newline', {'id': 'x\n'}, False),
            ('not-object', 'not-an-object', False),
        ]:
            case('fault-' + name, [(['items'], [item])], expected, kind='fault')
        driver = r'''
const fs=require('fs'),vm=require('vm'),ctx=vm.createContext({});
vm.runInContext(fs.readFileSync(process.argv[1],'utf8')+';globalThis.check={plan:validatePlan,fault:validateFaults};',ctx);
const inputs=JSON.parse(fs.readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(inputs.map(x=>{try{ctx.check[x.kind](x.data,x.asOf);return true;}catch(e){return false;}})));
'''
        r = subprocess.run(['node', '-e', driver, str(ROOT / 'scripts/file-store.js')],
                           input=json.dumps(fixtures, ensure_ascii=False), capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stderr)
        actual_js = json.loads(r.stdout)
        for fixture, js_ok in zip(fixtures, actual_js, strict=True):
            with self.subTest(case=fixture['name']):
                try:
                    if fixture['kind'] == 'plan':
                        validate_plan(fixture['data'], as_of=fixture['asOf'])
                    else:
                        validate_faults(fixture['data'])
                    py_ok = True
                except (ValueError, TypeError, KeyError):
                    py_ok = False
                self.assertEqual(py_ok, fixture['expected'], 'Python contract')
                self.assertEqual(js_ok, fixture['expected'], 'JS contract')

    def test_b5_legacy_state_merges_match_javascript_except_draft_event(self):
        p = self.p()
        p['weeks'][0]['note'] = 'current week'
        task_index(p)['1-2']['note'] = 'current task'
        p['dailyLogs'] = {'2026-09-06': {'note': 'current log', 'minutes': 10, 'keep': 1}}
        p['_orphans'] = [{'note': 'known orphan', 'id': 'removed-7', 'done': False}]
        payloads = [
            {'done': {}, 'notes': {'1': 'old week', '1-2': 'note only', 'song1': 'delivery note',
                                   '99': 'unknown week', 'no_hyphen': 'unknown id', '__proto__': 'not a prototype',
                                   'removed-7': 'known orphan'}, 'checkins': ['2026-09-06', '2026-09-06']},
            {'schema': 'self-evolution/plan90/v1', 'weeks': [{'n': 1, 'note': 'old\nweek', 'tasks': [
                {'id': '1-0', 'done': True, 'note': 'old\nnote', 'completedOn': '2026-09-06', 'evidence': ['artifact']},
                {'id': 'removed-9', 'done': False, 'note': 'orphan', 'extra': {'keep': 2}}]}],
             'dailyLogs': {'2026-09-06': {'note': 'old log', 'minutes': 25, 'newField': 3}},
             '_orphans': [{'id': 'archive', 'extra': True}], 'checkins': []},
        ]
        driver = r'''
const fs=require('fs'),vm=require('vm'),ctx=vm.createContext({});
vm.runInContext(fs.readFileSync(process.argv[1],'utf8')+';globalThis.convert=convertLegacy;',ctx);
const x=JSON.parse(fs.readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(x.payloads.map(d=>ctx.convert(d,x.current,'2026-09-06'))));
'''
        r = subprocess.run(['node', '-e', driver, str(ROOT / 'scripts/file-store.js')],
                           input=json.dumps({'current': p, 'payloads': payloads}), capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stderr)
        for payload, result in zip(payloads, json.loads(r.stdout), strict=True):
            expected = copy.deepcopy(p)
            import_plan_state(expected, payload, as_of='2026-09-06')
            self.assertEqual(result['history'][-1]['action'], 'legacy-import-draft')
            result['history'].pop()
            self.assertEqual(result, expected)

    def test_imported_fault_sample_types_are_validated_before_legacy_normalization(self):
        before = self.files()
        self.cli('fault', 'import', '--data', '{"items":[{"id":"sample1","symptom":"synthetic","isSample":"false"}]}', ok=False)
        self.assertEqual(before, self.files())



if __name__ == '__main__':
    unittest.main()
