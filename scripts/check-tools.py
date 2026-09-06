#!/usr/bin/env python3
"""Check executable scripts separately from embedded application/json blocks."""
import json
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ToolParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.scripts, self.active, self.external = [], None, []
        self.counts = {k: [0, 0] for k in ('div', 'table', 'script', 'style')}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.counts:
            self.counts[tag][0] += 1
        for key in ('src', 'href'):
            if attrs.get(key, '').startswith(('http:', 'https:', '//')):
                self.external.append(attrs[key])
        if tag == 'script':
            self.active = [attrs.get('type', 'text/javascript'), '']
            self.scripts.append(self.active)

    def handle_data(self, text):
        if self.active is not None:
            self.active[1] += text

    def handle_endtag(self, tag):
        if tag in self.counts:
            self.counts[tag][1] += 1
        if tag == 'script':
            self.active = None


def main():
    if not shutil.which('node'):
        print('需要 Node 才能检查 JavaScript 语法（仅维护测试依赖）。', file=sys.stderr)
        return 1
    errors = []
    for path in sorted((ROOT / 'tools').glob('*.html')):
        parser = ToolParser()
        parser.feed(path.read_text(encoding='utf-8'))
        if parser.external:
            errors.append(path.name + ' 引入外部资源')
        for tag, (op, cl) in parser.counts.items():
            if op != cl:
                errors.append(f'{path.name} <{tag}> 不平衡：{op}/{cl}')
        for kind, content in parser.scripts:
            if kind == 'application/json':
                try:
                    json.loads(content)
                except ValueError:
                    errors.append(path.name + ' 内嵌 JSON 无效')
                continue
            with tempfile.TemporaryDirectory() as tmp:
                js = Path(tmp) / 'tool.js'
                js.write_text(content, encoding='utf-8')
                result = subprocess.run(['node', '--check', str(js)], capture_output=True, text=True)
                if result.returncode:
                    errors.append(path.name + '\n' + result.stderr)
        print('已检查：' + path.name)
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print('通过：HTML 标签、内嵌 JSON、可执行 JS 语法、零外部资源。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
