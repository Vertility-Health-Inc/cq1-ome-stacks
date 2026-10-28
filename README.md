# CQ1 auto-stacks

Turns a Yokogawa CQ1 run's single-plane tiles into **one OME-TIFF per field**, with all
z-slices, timepoints and channels in one file. It runs automatically on new runs.

```
<run>/Image/W0014F0001T0001Z001C1.tif ...   →   <run>/Stacks/B02_f01.ome.tiff
```

- Axes are `TZCYX`. Fiji/Bio-Formats opens the files as hyperstacks.
- Pixel size and z-step come from the run's `MeasurementResult.ome.xml`.
- Wells are numbered 1-based, row-major over 12 columns (96-well): `W0014` → `B02`.
- Missing planes (for example, an aborted acquisition) are zero-filled and logged as `WARN`.

| File | What it does |
|---|---|
| `cq1_stacks.py` | The stacking script (manual or scan mode). |
| `launchd/com.vertility.cq1-stacks.plist` | macOS LaunchAgent that runs scan mode every 5 minutes. |

## Requirements

Python 3.10+ with `numpy` and `tifffile`. The `cellpose` conda env already has both.
The plist points at `~/miniforge3/envs/cellpose/bin/python`; replace `/Users/YOU` in it with your home folder.

## Manual use

```bash
~/bin/cq1_stacks.py "/path/to/<experiment>/<run>"
```

This works on any run, old or new. Stacks that already exist are skipped, so re-running resumes an interrupted job.

## Automatic use (new runs only)

```bash
cp cq1_stacks.py ~/bin/ && chmod +x ~/bin/cq1_stacks.py
cp launchd/com.vertility.cq1-stacks.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.vertility.cq1-stacks.plist
```

Every 5 minutes the agent runs `cq1_stacks.py --scan ~/Data --since <cutoff>`. It stacks a run
under `<root>/<experiment>/<run>/` when all of these are true:

- `MeasurementResult.ome.xml` exists. The CQ1 writes it last.
- That file is newer than `--since`. This keeps already-analyzed old runs from being stacked and filling the disk.
- Nothing in `Image/` has changed for `--quiet-min` minutes (default 5). This means copying has finished.
- `Stacks/.done` doesn't exist yet. Finished runs are never revisited.

Edit the paths and the `--since` cutoff in the plist for another machine or user. To see what it did:

```bash
tail -f ~/Library/Logs/cq1-stacks.log
```

To stop it:

```bash
launchctl bootout gui/$(id -u)/com.vertility.cq1-stacks
```

## License

BSD 3-Clause. See [LICENSE](LICENSE). Copyright (c) 2026 Vertility Health, Inc.
