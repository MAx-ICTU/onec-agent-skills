#!/usr/bin/env python3
"""Prepare a fresh isolated 1C test directory. Does not launch 1C."""
import argparse
from pathlib import Path
import shutil


def prepare(target):
    target = target.resolve()
    source = Path(__file__).resolve().parent
    project = source.parents[1]
    # Never reuse a database or overwrite an earlier run.
    target.mkdir(parents=True, exist_ok=False)
    (target / 'platform').mkdir()
    shutil.copytree(source / 'source', target / 'config')
    for path in (target / 'config').rglob('*'):
        if path.is_file():
            text = path.read_text(encoding='utf-8-sig')
            text = text.replace('{{RUN_ROOT}}', target.as_posix())
            text = text.replace('{{PROJECT_ROOT}}', project.as_posix())
            path.write_text(text, encoding='utf-8')
    for case in ('Q2', 'Q3', 'Q4', 'Q4-repeat'):
        packet = project / 'evals/query-forward' / case
        shutil.copytree(packet / 'input', target / case / 'input')
        (target / case / 'artifacts').mkdir()
        for name in ('proposed.query', 'proposed.bsl'):
            if (packet / 'artifacts' / name).exists():
                shutil.copyfile(packet / 'artifacts' / name, target / case / 'artifacts' / name)
    print('Prepared:', target)
    print('1C was NOT launched; create a NEW database at:', target / 'base')
    print('Results will be written to:', target / 'platform/results.txt')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path, help='New directory; must not already exist')
    args = parser.parse_args()
    prepare(args.target)
