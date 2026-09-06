#!/usr/bin/env python3
"""Generate read-only project views from canonical JSON.

Replaces the old HTML -> JSON regex extractor. This script never rewrites
progress state, never changes completion flags, and never uses today's date
as a reason to dirty an otherwise synchronized project.
"""
import argparse
import sys
from pathlib import Path
from project_data import ROOT, sync_views


def main():
    parser = argparse.ArgumentParser(description='JSON → Markdown / standalone HTML snapshots')
    parser.add_argument('--check', action='store_true', help='检查生成文件一致性，不写入任何内容')
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        changed = sync_views(args.root, check=args.check)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print('同步失败：' + str(exc), file=sys.stderr)
        return 1
    if args.check:
        print('需要同步：' + '、'.join(changed) if changed else '已同步；JSON 与只读视图一致')
        return 1 if changed else 0
    print('已生成：' + '、'.join(changed) if changed else '已同步，无需修改')
    print('JSON 未被改写；所有任务状态、稳定 ID、备注、证据与历史保持不变。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
