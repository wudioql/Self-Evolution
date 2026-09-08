#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Self-Evolution · 文档体检脚本

对应 AGENTS.md §6 / §6.1 / §7 / §8 / §9 与 .agents/skills/neat-freak 的自检项。
用法：
    python3 scripts/check-docs.py            # 检查，失败返回 1
    python3 scripts/check-docs.py --verbose  # 列出每一项的通过情况

退出码：0 = 全部通过；1 = 有 FAIL。
"""
import os
import re
import sys
import glob
import argparse
from pathlib import Path
from urllib.parse import unquote

parser = argparse.ArgumentParser(description='项目文档 / 隐私 / 生成视图体检')
parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
parser.add_argument('--verbose', action='store_true')
args = parser.parse_args()
ROOT = str(args.root.resolve())
VERBOSE = args.verbose
ALIAS = {
    '音乐手册': 'manuals/音乐学习手册.md', '音乐学习手册': 'manuals/音乐学习手册.md',
    '日语手册': 'manuals/日语学习手册.md', '日语学习手册': 'manuals/日语学习手册.md',
    'IPA手册': 'manuals/IPA与音韵学手册.md',
    '半导体手册': 'manuals/半导体设备成长手册.md',
    'AI手册': 'manuals/AI与工具手册.md', 'AI与工具手册': 'manuals/AI与工具手册.md',
}
results = []


def chk(cid, item, ok, detail=''):
    results.append((cid, item, bool(ok), detail))


def as_posix(p):
    # glob 在 Windows 返回反斜杠路径；文档 / HTML 字典键统一正斜杠（AUDIT.md / CHANGELOG.md 2026-09-07）
    return p.replace('\\', '/')


# Prune only known private/dependency/cache directories, not all dot-directories.
SKIP_DIRS = {'.git', '.backups', '__pycache__', 'node_modules', '.venv', 'venv', '.cache',
             '.pytest_cache', '.mypy_cache', '.ruff_cache', '.npm', '.next', 'coverage'}
TEXT_SUFFIXES = {'.md', '.html', '.json', '.jsonc', '.js', '.cjs', '.mjs', '.py', '.yml', '.yaml',
                 '.txt', '.css', '.svg', '.csv', '.toml', '.ini', '.cfg', '.xml', '.sh', '.ps1'}
TEXT_NAMES = {'.gitignore', '.gitattributes', '.editorconfig', 'LICENSE', 'Dockerfile'}
# 二进制内容却用文本后缀存档的文件，跳过 UTF-8 读取检查（2026-09-09）
SKIP_FILES = {'Self-Evolution.zip.txt'}
VENDOR = '.agents/skills/neat-freak/'


def private_path(relative):
    return any('.local.' in part or part == '.backups' for part in Path(relative).parts)


def project_texts():
    texts, errors = {}, []
    for directory, dirs, files in os.walk(ROOT, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and '.local.' not in d)
        for name in sorted(files):
            path = Path(directory) / name
            relative = path.relative_to(ROOT).as_posix()
            if private_path(relative) or name in SKIP_FILES or (path.suffix.lower() not in TEXT_SUFFIXES and name not in TEXT_NAMES):
                continue
            # Never follow a file link outside the inspected project.
            if not path.resolve().is_relative_to(Path(ROOT)):
                errors.append(relative + ' 指向项目外，未扫描')
                continue
            try:
                texts[relative] = path.read_text(encoding='utf-8')
            except (OSError, UnicodeError):
                errors.append(relative + ' 无法按 UTF-8 读取')
    return texts, errors


def upstream_reference(path):
    # General instructions/templates are not the project's learning policy.
    # Their real links and their full raw text STILL receive link/privacy checks.
    return path in (VENDOR + 'SKILL.md', VENDOR + 'LICENSE-upstream.md') or path.startswith(VENDOR + 'references/')


def blank_code(text):
    return ''.join('\n' if c == '\n' else ' ' for c in text)


def strip_fences(text):
    # Preserve line numbers. Support backtick/tilde fences, including long fences.
    result, fence = [], None
    for line in text.splitlines(keepends=True):
        match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*?)(?:\n)?$', line)
        if fence:
            result.append(blank_code(line))
            if match and match[1][0] == fence[0] and len(match[1]) >= fence[1] and not match[2].strip():
                fence = None
        elif match:
            fence = (match[1][0], len(match[1]))
            result.append(blank_code(line))
        else:
            result.append(line)
    return ''.join(result)


def link_targets(text):
    # A whole `[label](example)` in code is not a link. Code inside the label
    # is masked without discarding the surrounding real [label](destination).
    text = strip_fences(text)
    text = re.sub(r'(?<!`)(`+)(?!`)([\s\S]*?)\1(?!`)', lambda m: blank_code(m[0]), text)
    text = re.sub(r'<!--[\s\S]*?-->', lambda m: blank_code(m[0]), text)
    return [m[1].strip('<>') for m in re.finditer(r'!?\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^\s)]+)(?:\s+[\"\'][^\n]*[\"\'])?\s*\)', text)]


def anchors(path):
    text = path.read_text(encoding='utf-8')
    ids = set(re.findall(r'\bid=[\"\']([^\"\']+)[\"\']', text))
    if path.suffix.lower() != '.md':
        return ids
    counts = {}
    for heading in re.findall(r'^ {0,3}#{1,6}\s+(.+?)(?:\s+#+)?\s*$', strip_fences(text), re.M):
        heading = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', heading)
        heading = re.sub(r'<[^>]*>', '', heading)
        slug = ''.join(c for c in heading.lower().strip() if c.isalnum() or c in '_- ').replace(' ', '-')
        n = counts.get(slug, 0)
        ids.add(slug + (f'-{n}' if n else ''))
        counts[slug] = n + 1
    return ids


os.chdir(ROOT)
public, read_errors = project_texts()
all_docs = {f: s for f, s in public.items() if Path(f).suffix.lower() == '.md'}
docs = {f: s for f, s in all_docs.items() if not upstream_reference(f)}
# Private generated views also need syntax/structural checks, but never a public scan.
# glob 在 Windows 返回反斜杠路径：键先归一化为正斜杠，再经 ROOT 重定位读取
# （直接 Path(f) 读反斜杠相对路径在非 Windows 上不存在，且字典键与文档约定不一致）
htmls = {p: (Path(ROOT) / p).read_text(encoding='utf-8')
         for p in map(as_posix, sorted(glob.glob('tools/*.html')))}
base = os.path.basename
chk('扫描', '公开文本可读取（含隐藏目录；排除私有 / 缓存）', not read_errors, '; '.join(read_errors[:5]))


def sections(path):
    s = Path(path).read_text(encoding='utf-8')
    return {m.group(1) for m in re.finditer(r'^#{2,4} (?:第 ?)?(\d+(?:\.\d+)?)[. ·b]', s, re.M)}


# ── §8 actual Markdown links (including hidden and vendored documents) ───
broken = []
for f, s in all_docs.items():
    for target in link_targets(s):
        if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target) or target.startswith('//'):
            continue
        local, _, fragment = target.partition('#')
        local = unquote(local.split('?', 1)[0])
        path = (Path(f).parent / local).resolve() if local else Path(f).resolve()
        if not path.is_relative_to(Path(ROOT)) or not path.exists():
            broken.append(f'{f} -> {target}')
        elif fragment:
            try:
                valid = path.is_file() and unquote(fragment) in anchors(path)
            except (OSError, UnicodeError):
                valid = False
            if not valid:
                broken.append(f'{f} -> {target}（锚点不存在）')
chk('§8', '文档内实际链接与锚点有效（代码示例除外）', not broken, '; '.join(broken[:5]))


# ── §8 章节引用（§N.M 指向的章节必须存在）────────────────
cache, miss = {}, []
for f, s in docs.items():
    for nm, sc in re.findall(r'\[`?([^`\]]*手册)`?\]\([^)]*\)\s*§\s*(\d+(?:\.\d+)?)', s):
        t = ALIAS.get(nm)
        if not t:
            continue
        cache.setdefault(t, sections(t))
        if sc not in cache[t]:
            miss.append(f'{f}: {nm} §{sc}')
    for sc in re.findall(r'(?:本文|见|→)\s*§\s*(\d+(?:\.\d+)?)', s):
        cache.setdefault(f, sections(f))
        if sc not in cache[f]:
            miss.append(f'{f}: 自引 §{sc}')
chk('§8', '章节引用全部落位', not miss, '; '.join(miss[:5]))

# ── §2 速查层：每节必须有 →（§11 文件在哪 为例外）────────
s00 = docs.get('00-速查表.md', '')
miss_arrow = [b.split('\n')[0].strip() for b in re.split(r'^## ', s00, flags=re.M)[1:]
              if '→' not in b and '文件在哪' not in b.split('\n')[0]]
chk('§2', '00 速查表每节都有 → 指向', not miss_arrow, f'缺 {miss_arrow}')

# ── §2 执行层：不在 03 里重复做复选框；04 有复选框 ───────
chk('§2', '03 不重复维护复选框（JSON 为唯一进度源）',
    docs.get('03-90天计划.md', '').count('- [ ]') == 0)
chk('§2', '04 有 - [ ] 可勾选项', '- [ ]' in docs.get('04-扒带作业单.md', ''))

# ── §6.1 单一真相源：执行层不能出现"怎么做" ──────────────
METHOD = ['只准做这 4 件事', 'Step 0 · 准备', 'To Pitch', '先自己把根音唱出来',
          'Praat 操作步骤', 'Transcribe! 的算法', '卡点速查表']
leak = []
for f in ['03-90天计划.md', '04-扒带作业单.md']:
    for line in docs.get(f, '').split('\n'):
        for m in METHOD:
            if m in line and not re.search(r'手册\s*\*{0,2}§|\]\([^)]*手册\.md\)|→', line):
                leak.append(f'{base(f)}: {m}')
chk('§6.1', '执行层无「怎么做」残留（指针行不算）', not leak, str(sorted(set(leak))))

# ── §6 手册模板：定位说明 + 与执行层的对接（三列固定）────
bad_tpl = []
for f in sorted(glob.glob('manuals/*.md')):
    f = as_posix(f)
    s = docs[f]
    if not ('定位说明' in s[:1500] or '不通读' in s[:1500]):
        bad_tpl.append(f'{base(f)} 缺定位说明')
    if '与执行层的对接' not in s:
        bad_tpl.append(f'{base(f)} 缺对接章节')
    elif not re.search(r'与执行层的对接[\s\S]{0,400}?\|\s*时间\s*\|\s*执行层动作\s*\|\s*本手册对应章节\s*\|', s):
        bad_tpl.append(f'{base(f)} 对接表列不齐')
chk('§6', '5 份手册符合模板（定位说明 + 对接表）', not bad_tpl, '; '.join(bad_tpl))

# ── §7 工具：零外部依赖 + localStorage 降级 + 标签平衡 ───
bad_html = []
for f, s in htmls.items():
    if re.findall(r'(?:src|href)="(https?://[^"]+)"', s):
        bad_html.append(f'{base(f)} 有外部依赖')
    if not re.search(r'try\s*\{[^}]*localStorage', s, re.S):
        bad_html.append(f'{base(f)} localStorage 无降级')
    for tag in ('div', 'table', 'script', 'style'):
        o, c = len(re.findall(rf'<{tag}[\s>]', s)), len(re.findall(rf'</{tag}>', s))
        if o != c:
            bad_html.append(f'{base(f)} <{tag}> {o}/{c} 不平衡')
chk('§7', 'tools/*.html 零依赖 + 降级 + 标签平衡', not bad_html, '; '.join(bad_html))

# ── §9 禁区（排除 AGENTS 自身规则文本与「不碰/不买」上下文）
BANS = [('新增第五条轨道', r'轨道\s*5|第五条轨道'),
        ('建议买设备/软件/插件', r'值得买|建议买|推荐购买'),
        ('需联网资源', r'需要联网|必须联网'),
        ('报班/考证/找老师', r'报班|考证|找个?老师'),
        ('建议学编程', r'建议你?学(?:一?[下点])?(?:编程|Python)')]
hits = []
for label, pat in BANS:
    for f, s in docs.items():
        if base(f) == 'AGENTS.md':
            continue
        for line in s.split('\n'):
            if re.search(pat, line) and not re.search(r'不碰|不买|90 天内|2027', line):
                hits.append(f'{label} @ {base(f)}')
chk('§9', '无禁区内容', not hits, '; '.join(sorted(set(hits))[:5]))

# ── §4 轨道上限 ──────────────────────────────────────────
tracks = {int(x) for x in re.findall(r'轨道\s*([1-9])', '\n'.join(docs.values()))}
chk('§4', '轨道 ≤ 4 条', max(tracks, default=0) <= 4, str(sorted(tracks)))

# ── neat-freak 自检项：无相对时间 ────────────────────────
REL = r'今天|昨天|明天|刚刚|上周|本周|这周|下周|上周内|近期|不久|过几天|today|yesterday|recently'
EVENT = r'上线|发布|完成|新增|修改|更新|决定|改为|已经|已完成'


# 阻塞：相对时间 + 事件陈述（这类会腐烂，必须写成绝对日期）
rot = []
for f, s in docs.items():
    for i, line in enumerate(strip_fences(s).split('\n'), 1):
        if re.search(REL, line) and re.search(EVENT, line) \
                and not re.search(r'\d{4}-\d{2}-\d{2}', line):
            rot.append(f'{base(f)}:{i}')
chk('neat-freak', '无「相对时间 + 事件陈述」（会腐烂）', not rot, '; '.join(rot[:5]))

# 提示（不阻塞）：流程 / 标签里的"今天 / 下周"属正常用法
adv = [f'{base(f)}:{i}' for f, s in docs.items()
       for i, line in enumerate(strip_fences(s).split('\n'), 1) if re.search(REL, line)]
if adv and VERBOSE:
    print(f'  [WARN] neat-freak 相对时间（流程/标签用法，共 {len(adv)} 处，不阻塞）')

# ── 隐私：真值不得出现在公开文件里（用 *.local.md 反查）──
local_maps = sorted(glob.glob('*.local.md'))
secrets = []
if local_maps:
    for lf in local_maps:
        for row in re.findall(r'^\|\s*(.+?)\s*\|\s*(.+?)\s*\|', open(lf, encoding='utf-8').read(), re.M):
            val = row[1].strip()
            if not val or val.startswith(('---', '（', '真值')) or set(val) <= set('-: '):
                continue
            secrets.append(val)
    leaks = []
    for f, txt in public.items():
        for val in secrets:
            if val in txt:
                leaks.append(f'{f} 含本地映射表真值（不在日志回显）')
    chk('隐私', f'公开文件无真值泄漏（{len(secrets)} 条真值反查）', not leaks, '; '.join(leaks[:5]))
else:
    if VERBOSE:
        print('  [ -- ] 隐私        无 *.local.md，跳过（CI 里属正常）')

# 隐私：*.local.md 不得被 git 跟踪
if os.path.isdir('.git'):
    import subprocess
    try:
        result = subprocess.run(['git', 'ls-files', '*.local.*', '**/.backups/**'], capture_output=True, text=True)
        tracked = result.stdout.strip()
        chk('隐私', '私有文件与备份未被 git 跟踪', result.returncode == 0 and not tracked, tracked or ('无法检查 Git 状态' if result.returncode else ''))
    except OSError:
        chk('隐私', '私有文件与备份未被 git 跟踪', False, 'Git 不可用，未确认跟踪状态')

# ── 文件型记录：JSON 与生成视图必须一致 ───────────────────
try:
    from project_data import sync_views
    stale = sync_views(Path(ROOT), check=True)
    chk('数据', 'JSON 校验与只读视图一致（同步检查无写入）', not stale, '; '.join(stale))
    import json
    public_html = htmls.get('tools/故障模式库.html', '')
    match = re.search(r'<script type="application/json" id="project-data">(.*?)</script>', public_html, re.S)
    shell = json.loads(match.group(1)) if match else {}
    chk('隐私', '公开故障工具壳不嵌入真实数据或私有配置',
        shell.get('items') == [] and shell.get('history') == [] and shell.get('config', {}).get('sensitive') == [])
except (ValueError, KeyError, TypeError, OSError) as exc:
    chk('数据', 'JSON 与生成视图校验', False, str(exc))

# ── 输出 ─────────────────────────────────────────────────
passed = sum(1 for r in results if r[2])
for cid, item, ok, detail in results:
    if VERBOSE or not ok:
        mark = 'PASS' if ok else 'FAIL'
        line = f'  [{mark}] {cid:<10s} {item}'
        if detail and not ok:
            line += f'\n         → {detail}'
        for secret in sorted(set(secrets), key=len, reverse=True):
            line = line.replace(secret, '***')
        print(line)
if VERBOSE:
    print(f'  扫描 {len(public)} 个公开文本，其中 Markdown {len(all_docs)} 个（含隐藏目录；上游文档也查真实链接与隐私）。')
print(f'\n  {passed}/{len(results)} 通过')
sys.exit(0 if passed == len(results) else 1)
