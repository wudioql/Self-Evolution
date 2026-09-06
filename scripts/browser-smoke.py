#!/usr/bin/env python3
"""Optional deterministic real-browser regression; never edits real project data.

Maintainer: python3 -m pip install playwright && python3 -m playwright install chromium
Run: python3 scripts/browser-smoke.py [--date YYYY-MM-DD] [--screenshots /local/path]
Defaults to Day 0, W2, Day 98 and after the plan, all using reset temporary fixtures.
Permission / file-write failures are separately modeled in test-file-store.cjs.
"""
import argparse
import html
import json
import shutil
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright
from project_data import (ROOT, TZ, PLAN_PATH, FAULT_PATH, load, dump, parse_date, tasks,
                          calc_stats, empty_faults, sync_views)


def fixture(root):
    for rel in ('tools/90天进度表.html', 'tools/故障模式库.html', 'scripts/file-store.js', '03-90天计划.md'):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    p = load(ROOT, PLAN_PATH)
    # A clock fixed before the user's later real completions must not invalidate
    # or expose their state. Test the schedule with explicitly synthetic empty state.
    for t in tasks(p) + p['deliverables']:
        t.update(done=False, completedOn=None, note='', evidence=[])
    for w in p['weeks']:
        w['note'] = ''
    p.update(checkins=[], dailyLogs={}, overrides=[], history=[], _orphans=[])
    p['meta'].update(revision=1, updated=p['meta']['day0'])
    p['stats'] = calc_stats(p)
    for rel, value in ((PLAN_PATH, p), (FAULT_PATH, empty_faults())):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dump(value), encoding='utf-8')
    sync_views(root)
    return p


def set_clock(page, ds):
    page.clock.install(time=datetime.combine(parse_date(ds), time(12), tzinfo=TZ))


def show_task(page, tid='1-0'):
    # Production should still open the current week. Tests explicitly open their
    # target's week instead of relying on W1 happening to be current.
    week = page.locator('.week').filter(has=page.locator('#task-' + tid))
    header = week.locator('.whead')
    if header.get_attribute('aria-expanded') != 'true':
        header.click()
    return page.locator('#task-' + tid + ' .check-button')


def run_scene(browser, root, p, ds, screenshots=None):
    context = browser.new_context(viewport={'width': 1280, 'height': 960}, timezone_id='Asia/Shanghai', locale='zh-CN')
    context.set_offline(True)
    errors = []
    try:
        page = context.new_page()
        set_clock(page, ds)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('dialog', lambda dialog: dialog.accept())
        page.goto((root / 'tools/90天进度表.html').as_uri())
        page.wait_for_selector('#dailyTitle')
        assert page.evaluate('projectToday()') == ds
        assert page.locator('#weeks .week').count() == len(p['weeks'])
        assert '文件快照' in page.locator('#sourceStatus').inner_text()
        before = page.evaluate('JSON.stringify(fs.data)')
        show_task(page).click()
        assert page.evaluate('JSON.stringify(fs.data)') == before
        assert '只读快照' in page.locator('#sourceStatus').inner_text()
        page.locator('#dailyDate').fill(p['meta']['day1'])
        page.locator('#dailyDate').dispatch_event('change')
        assert 'Day 1' in page.locator('#dailyTitle').inner_text()
        page.locator('#dailyDate').fill(p['meta']['day90'])
        page.locator('#dailyDate').dispatch_event('change')
        assert 'Day 90' in page.locator('#dailyTitle').inner_text()
        assert '六项交付' in page.locator('#dailyCheckpoints').inner_text()
        page.evaluate("ds=>{selectedDate=ds;$('dailyDate').value=ds;fs.refresh()}", ds)
        if screenshots:
            page.screenshot(path=str(screenshots / ('progress-' + ds + '-desktop.png')))

        page.evaluate('fs.enableDraft()')
        show_task(page).click()
        page.wait_for_function("fs.data.weeks.flatMap(w=>w.tasks).find(t=>t.id==='1-0').done===true")
        assert '未写入项目' in page.locator('#sourceStatus').inner_text()
        page.reload()
        page.wait_for_selector('#weeks .week')
        assert page.evaluate('JSON.stringify(fs.data)') == before
        # Exercise the actual restore button, not just presence of cached JSON.
        page.locator('details summary').click()
        page.locator('#restoreBtn').click()
        page.wait_for_function("fs.mode==='draft'&&fs.data.weeks.flatMap(w=>w.tasks).find(t=>t.id==='1-0').done")
        page.reload()
        page.wait_for_selector('#weeks .week')
        assert page.evaluate('JSON.stringify(fs.data)') == before

        legacy = {'done': {}, 'notes': {'1-2': 'synthetic notes-only import'}, 'checkins': []}
        page.set_input_files('#impFile', {'name': 'legacy.local.json', 'mimeType': 'application/json', 'buffer': dump(legacy).encode()})
        page.wait_for_function("fs.mode==='draft'&&fs.data.weeks.flatMap(w=>w.tasks).find(t=>t.id==='1-2').note==='synthetic notes-only import'")
        assert page.evaluate("fs.data.weeks.flatMap(w=>w.tasks).find(t=>t.id==='1-2').done") is False
        imported = page.evaluate('JSON.stringify(fs.data)')
        bad = {'done': {'1-0': True}, 'notes': {}, 'checkins': ['2099-01-01']}
        page.set_input_files('#impFile', {'name': 'bad.local.json', 'mimeType': 'application/json', 'buffer': dump(bad).encode()})
        page.wait_for_function("document.getElementById('sourceStatus').textContent.includes('导入失败')")
        assert page.evaluate('JSON.stringify(fs.data)') == imported
        page.reload()
        page.wait_for_selector('#weeks .week')

        # B6: compare publication/acceptance with unrelated housekeeping in memory.
        result = page.evaluate("""() => {
          const d=deepCopy(fs.data);
          d.weeks.flatMap(w=>w.tasks).forEach(t=>{if(t.track==='sound')t.done=true;});
          const paused=projectDayInfo(d,'2026-10-16');
          d.weeks.flatMap(w=>w.tasks).find(t=>t.id==='4-5').done=true;
          d.deliverables.find(d=>d.id==='song1').done=true;
          const resumed=projectDayInfo(d,'2026-10-16');
          return {paused:paused.ipaPaused,blocked:!paused.actions.some(a=>a.taskId==='6-5'),resumed:resumed.actions.some(a=>a.taskId==='6-5')};
        }""")
        assert result == {'paused': True, 'blocked': True, 'resumed': True}
        page.set_viewport_size({'width': 390, 'height': 844})
        page.evaluate('window.scrollTo(0,0)')
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
        if screenshots:
            page.screenshot(path=str(screenshots / ('progress-' + ds + '-mobile.png')))

        page.set_viewport_size({'width': 1280, 'height': 960})
        page.goto((root / 'tools/故障模式库.html').as_uri())
        assert page.evaluate('fs.data.items.length') == 0
        page.evaluate('fs.enableDraft()')
        page.get_by_role('button', name='＋ 新增记录', exact=True).click()
        page.locator('#f_symptom').fill('浏览器测试记录 <script>不执行</script>')
        page.locator('#f_eqType').select_option('PECVD')
        page.get_by_role('button', name='保存（Ctrl+S）', exact=True).click()
        page.wait_for_function('fs.data.items.length===1')
        for key in ('isSolved', 'isRecurring', 'downtimeMin'):
            assert page.evaluate('key=>fs.data.items[0][key]', key) is None
        assert '<script>不执行</script>' in page.locator('#list').inner_text()
        page.locator('#filters').get_by_role('button', name='PECVD', exact=True).click()
        assert page.locator('#list .card').count() == 1
        page.locator('#q').fill('不存在的搜索')
        assert page.locator('#list .card').count() == 0
        page.locator('#q').fill('浏览器测试')
        assert page.locator('#list .card').count() == 1
        page.locator('#list').get_by_role('button', name='编辑', exact=True).first.click()
        page.locator('#delBtn').click()
        page.wait_for_function('fs.data.items.length===0')
        page.reload()
        assert page.evaluate('fs.data.items.length') == 0
        if screenshots:
            page.screenshot(path=str(screenshots / ('faults-' + ds + '-desktop.png')))

        frame_page = context.new_page()
        set_clock(frame_page, ds)
        frame_page.on('pageerror', lambda error: errors.append(str(error)))
        content = (root / 'tools/90天进度表.html').read_text(encoding='utf-8')
        frame_page.set_content('<iframe sandbox="allow-scripts" style="width:100%;height:900px" srcdoc="' + html.escape(content, quote=True) + '"></iframe>')
        frame = frame_page.frame_locator('iframe')
        frame.locator('#weeks .week').first.wait_for()
        assert frame.locator('#weeks .week').count() == len(p['weeks'])
        assert '文件快照' in frame.locator('#sourceStatus').inner_text()
        assert not errors, errors
    finally:
        context.close()
    print('PASS Chromium clock ' + ds + ': offline, desktop/mobile, snapshot/draft/restore/import, IPA gating, fault CRUD, opaque iframe')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', help='Optional test clock override; never changes plan dates')
    parser.add_argument('--screenshots', type=Path)
    args = parser.parse_args()
    if args.date:
        parse_date(args.date)
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)
    protected = {rel: (ROOT / rel).read_bytes() if (ROOT / rel).exists() else None for rel in (PLAN_PATH, FAULT_PATH)}
    try:
        with tempfile.TemporaryDirectory(prefix='selfevo-browser-') as tmp:
            root = Path(tmp)
            p = fixture(root)
            dates = [args.date] if args.date else [p['meta']['day0'],
                (parse_date(p['meta']['day1']) + timedelta(days=7)).isoformat(), p['meta']['end'],
                (parse_date(p['meta']['end']) + timedelta(days=1)).isoformat()]
            # Even the disposable fixture JSON must remain unwritten by browser drafts.
            fixture_bytes = {rel: (root / rel).read_bytes() for rel in protected}
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                try:
                    for ds in dates:
                        run_scene(browser, root, p, ds, args.screenshots)
                finally:
                    browser.close()
            for rel, value in fixture_bytes.items():
                assert (root / rel).read_bytes() == value
    finally:
        for rel, value in protected.items():
            actual = (ROOT / rel).read_bytes() if (ROOT / rel).exists() else None
            assert actual == value, 'Browser test changed the master: ' + rel
    print('PASS: temporary fixtures cleaned; canonical plan and private faults unchanged.')


if __name__ == '__main__':
    main()
