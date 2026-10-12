# Link ECU tune tooling

`pclink.py` reads and edits PCLink tune files (`.pclx` G4X, `.pcl5` G5) directly, so an AI
can inspect and change a tune without the GUI. Stdlib only. PCLink is installed at
`C:\Link G5\PCLink G5` (override with `PCLINK_DIR`); test tune:
`C:\Link G5\PCLink G5\Use me as a test tune\BMW E30.pclx`.

```
python pclink.py info  TUNE                 # ECU, firmware, serial
python pclink.py find  TUNE fuel table      # search settings by words -> DataId, menu path, value
python pclink.py get   TUNE 2365 [--json]   # one setting / table with its axes
python pclink.py set   TUNE 2365 31.5 --cell ROW COL   # table cell (0-based)
python pclink.py set   TUNE 3737 Traditional           # option by label or index; numbers; text
python pclink.py dump  TUNE all.json        # every editable setting as JSON
python test_pclink.py                       # self-check, must print "ok"
```

`python pclink_gui.py TUNE` opens the offline PCLink look-alike. It auto-switches to `<name>.ai.pclx`
when that file appears or changes, and outlines what differs from the original - so after a `set`, tell
the user to look at the window rather than describing the change at length.

Bulk edits: `from pclink import Tune` -> `t.get(id)`, `t.table(id)`, `t.set(id, v)`,
`t.set_table(id, rows)` (None = keep), `t.save()`.

Rules that must hold:
- Settings are addressed by DataId; always `find`/`get` first and quote the old value before changing it.
- `set`/`save` write `<name>.ai.pclx` beside the original and never overwrite a non-`.ai` file.
- Values are in the units PCLink shows; they are range-checked against PCLink's Min/Max and snapped to the ECU step.
- Password protected tunes are refused and password fields are hidden. Do not work around this.
- A changed tune is untested until the user has opened it in PCLink, reviewed it and logged the engine. Say so every time; never describe an edit as safe to drive on.
- For what a setting does, use the PCLink help (`Help_File_ENG.chm`), not guesses.

File format notes live in the `pclink.py` module docstring. `graphify-out/` holds the knowledge graph of this folder.
