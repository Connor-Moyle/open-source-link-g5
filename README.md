# Open Source Link G5

this was only created as i have a misfire i can not figure out for the life of me, tunners havent been able to figure it out so maybe ai can, this is purely a way for a ai to be able to open a tune file and see if anything is not correct

Unofficial tools for reading and editing Link ECU **PCLink** tune files (`.pclx` G4X, `.pcl5` G5)
outside of PCLink - from the command line, from Python, from an AI assistant, or in an offline
PCLink-style window.

> Not made by, endorsed by or affiliated with Link Engine Management. "Link" and "PCLink" are their trademarks.
> You need your own installed copy of PCLink: setting names, units, limits and layouts are read from it at
> runtime and are not included here.

**A wrong tune can destroy an engine.** Nothing here talks to an ECU. Always open an edited file in the
real PCLink, review it, and log the engine before trusting it.

## What is here

| File | What it does |
|---|---|
| `pclink.py` | Decode/encode tune files, look up settings by name, change values and table cells (CLI + `Tune` class). Stdlib only. |
| `pclink_gui.py` | Offline PCLink look-alike (tkinter). Loads your PCLink layout files, shows tables and value lists, lets you edit. |
| `test_pclink.py` | Self-check against a tune from your install. |
| `CLAUDE.md` | Instructions for AI coding agents working in this folder. |

## Use

Python 3.10+ on Windows. Set `PCLINK_DIR` if PCLink is not in `C:\Link G5\PCLink G5`.

```
python pclink.py find  my.pclx fuel table        # search settings
python pclink.py get   my.pclx 2365              # show Fuel Table 1 with axes
python pclink.py set   my.pclx 2365 31.5 --cell 3 4
python pclink.py dump  my.pclx all.json          # everything as JSON
python pclink_gui.py   my.pclx                   # the window
```

No Python? Download `OpenLinkG5.exe` from the Releases page and open a tune with it (or drag a tune onto it).
Build it yourself with `pip install pyinstaller` then
`pyinstaller --onefile --windowed --name OpenLinkG5 pclink_gui.py`.

Edits are written to `my.ai.pclx`; an existing file that is not an `.ai` copy is never overwritten.
The window follows that file automatically and outlines every value that differs from the original,
so you can watch and review changes an AI makes.

In the window: `F12` ECU Settings tree (with search), double-click a setting to edit, click/drag cells in a
table then type a value (`+n`, `-n`, `*n` adjust the selection), `PgUp`/`PgDn` nudge, `Ctrl+C`/`Ctrl+V`,
`Ctrl+Z` undo, `Ctrl+S` save, double-click an axis label to change a breakpoint.

## Not supported

Live ECU connection, store/firmware, logging and log files, gauges, time plots, mixture map, trigger scope,
CAN stream files, password protected tunes and files saved with "Save as Encrypted". Those menu entries are
shown greyed out.

## File format

A tune is XML (`<LinkStorage>` with a `<Memory>` header and a `<Map>` of `<D{DataId}>` entries) wrapped in
XXTEA over the whole file: three little-endian header words `[random, payload length, 0]`, then the XML, zero
padded. See the top of `pclink.py`.

MIT licensed.
