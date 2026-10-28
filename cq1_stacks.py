#!/usr/bin/env python3
"""Concatenate Yokogawa CQ1 single-plane tiles into one OME-TIFF per field.

Input:  <run>/Image/W0014F0001T0001Z001C1.tif ...
Output: <run>/Stacks/B02_f01.ome.tiff  (axes TZCYX, pixel sizes from MeasurementResult.ome.xml)

Usage:
  cq1_stacks.py RUN_DIR [RUN_DIR ...]         stack these runs now (any age)
  cq1_stacks.py --scan ROOT --since DATETIME  stack finished runs under ROOT/<exp>/<run>/
                                              whose acquisition ended after DATETIME
                                              (this is what the launchd watcher calls)

A run counts as finished when MeasurementResult.ome.xml exists (the CQ1 writes it
last) and nothing in Image/ has changed for --quiet-min minutes. Finished runs
get Stacks/.done and are never revisited; an interrupted run resumes where it
stopped because existing stacks are skipped.
"""
import argparse
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import tifffile

TILE = re.compile(r'W(\d+)F(\d+)T(\d+)Z(\d+)C(\d+)\.tif$')
ROWS = 'ABCDEFGHIJKLMNOP'


def log(msg):
    print(f'{datetime.now():%Y-%m-%d %H:%M:%S} {msg}', flush=True)


def pixel_sizes(run):
    """(xy, z) in µm from the CQ1's OME metadata; z defaults to 1 for single-plane runs."""
    xml = (run / 'MeasurementResult.ome.xml').read_text(errors='ignore')
    def get(key, default):
        m = re.search(rf'{key}="([\d.]+)"', xml)
        return float(m.group(1)) if m else default
    return get('PhysicalSizeX', 1.0), get('PhysicalSizeZ', 1.0)


def well_name(w, ncols=12):
    # CQ1 numbers wells 1-based, row-major (96-well: 12 columns)
    return f'{ROWS[(w - 1) // ncols]}{(w - 1) % ncols + 1:02d}'


def stack_run(run):
    run = Path(run)
    src, out = run / 'Image', run / 'Stacks'
    groups = defaultdict(dict)
    for p in src.glob('W*.tif'):
        m = TILE.match(p.name)
        if m:
            w, f, t, z, c = map(int, m.groups())
            groups[(w, f)][(t, z, c)] = p
    if not groups:
        log(f'SKIP {run}: no tiles in Image/')
        return False
    xy, dz = pixel_sizes(run)
    out.mkdir(exist_ok=True)
    log(f'START {run} ({len(groups)} fields, xy={xy} µm, z={dz} µm)')
    n = 0
    for (w, f), d in sorted(groups.items()):
        name = f'{well_name(w)}_f{f:02d}.ome.tiff'
        dst = out / name
        if dst.exists():
            continue
        T = sorted({k[0] for k in d}); Z = sorted({k[1] for k in d}); C = sorted({k[2] for k in d})
        missing = [k for k in ((t, z, c) for t in T for z in Z for c in C) if k not in d]
        if missing:
            log(f'WARN {name}: {len(missing)} planes missing (zero-filled): {missing[:5]}')
        first = tifffile.imread(next(iter(d.values())))
        arr = np.zeros((len(T), len(Z), len(C)) + first.shape, first.dtype)
        for (t, z, c), p in d.items():
            arr[T.index(t), Z.index(z), C.index(c)] = tifffile.imread(p)
        tmp = out / (name + '.tmp')
        tifffile.imwrite(tmp, arr, ome=True, photometric='minisblack', metadata={
            'axes': 'TZCYX',
            'PhysicalSizeX': xy, 'PhysicalSizeXUnit': 'µm',
            'PhysicalSizeY': xy, 'PhysicalSizeYUnit': 'µm',
            'PhysicalSizeZ': dz, 'PhysicalSizeZUnit': 'µm',
            'Channel': {'Name': [f'C{c}' for c in C]}})
        tmp.rename(dst)
        n += 1
    (out / '.done').write_text(f'{datetime.now().isoformat()}\n')
    log(f'DONE {run}: wrote {n} stacks')
    return True


def finished_runs(root, since, quiet_min):
    """Runs under root/<exp>/<run>/ that ended after `since`, are quiet, and not yet stacked."""
    now = time.time()
    for xml in sorted(Path(root).glob('*/*/MeasurementResult.ome.xml')):
        run = xml.parent
        if (run / 'Stacks' / '.done').exists() or xml.stat().st_mtime < since:
            continue
        img = run / 'Image'
        if not img.is_dir():
            continue
        newest = max([img.stat().st_mtime] + [p.stat().st_mtime for p in img.iterdir()])
        if now - newest < quiet_min * 60:
            log(f'WAIT {run}: Image/ changed {int((now - newest) / 60)} min ago')
            continue
        yield run


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('runs', nargs='*', type=Path)
    ap.add_argument('--scan', type=Path, help='root folder holding <experiment>/<run>/ dirs')
    ap.add_argument('--since', help='only runs finished after this, e.g. 2026-10-19T16:50')
    ap.add_argument('--quiet-min', type=float, default=5)
    a = ap.parse_args()
    if a.scan:
        if not a.since:
            ap.error('--scan needs --since so old runs are never touched')
        since = datetime.fromisoformat(a.since).timestamp()
        for run in finished_runs(a.scan, since, a.quiet_min):
            stack_run(run)
    for run in a.runs:
        stack_run(run)
    if not a.scan and not a.runs:
        ap.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
