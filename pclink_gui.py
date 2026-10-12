"""Offline PCLink look-alike: view and edit a Link ECU tune using PCLink's own layout files.

    python pclink_gui.py [tune.pclx] [layout.llf5]

Edits made elsewhere (e.g. by an AI running pclink.py) are picked up automatically:
when a newer "<name>.ai.pclx" appears beside the open tune, the window switches to it
and outlines everything that differs from the original.
"""
import os, sys, tkinter as tk
import xml.etree.ElementTree as ET
from tkinter import filedialog, messagebox, simpledialog, ttk

import pclink
from pclink import Tune

BG, PANEL, BAR, FG, SEL = '#000000', '#000000', '#404040', '#ffffff', '#1e90ff'
ROW_COLOURS = ['#33ff33', '#3399ff', '#ffff33', '#ff33ff', '#ffffff', '#33ffff', '#ff9933', '#999933']
FONT, BOLD = ('Segoe UI', 9), ('Segoe UI', 9, 'bold')
LIVE_ONLY = 'needs a live ECU or a log file - not available offline'
OPTIONS_XML = os.path.expandvars(r'%APPDATA%\PCLink\Options2.xml')


def heat(f):
    """0..1 -> blue, cyan, green, yellow, red (PCLink's table colours)."""
    stops = [(0, 0, 255), (0, 255, 255), (0, 255, 0), (255, 255, 0), (255, 0, 0)]
    f = min(max(f, 0), 1) * (len(stops) - 1)
    i = min(int(f), len(stops) - 2)
    a, b = stops[i], stops[i + 1]
    return '#%02x%02x%02x' % tuple(int(a[k] + (b[k] - a[k]) * (f - i)) for k in range(3))


def fmt(s):
    """Display text for a pclink.Tune.get() result."""
    if s['kind'] == 'table':
        return f'[table {len(s["rows"])} x {len(s["rows"][0])}]'
    v = s.get('value_label')
    if v is None:
        v = s['value']
        if isinstance(v, float):
            v = f'{v:g}'
    return f'{v} {s["units"] or ""}'.strip()


class Panel(tk.Frame):
    """A PCLink view: dark title bar + black body."""

    def __init__(self, app, title='', closable=False):
        super().__init__(app.desk, bg=PANEL, highlightbackground=BAR, highlightthickness=1)
        self.app = app
        bar = tk.Frame(self, bg=BAR, height=18)
        bar.pack(fill='x')
        tk.Label(bar, text=title, bg=BAR, fg=FG, font=FONT).pack(side='left', padx=4)
        if closable:
            x = tk.Label(bar, text='✕', bg=BAR, fg=FG, font=FONT, cursor='hand2')
            x.pack(side='right', padx=4)
            x.bind('<Button-1>', lambda e: self.destroy())
            bar.bind('<B1-Motion>', self._drag)
        self.body = tk.Frame(self, bg=PANEL)
        self.body.pack(fill='both', expand=True)

    def _drag(self, e):
        self.place(x=self.winfo_x() + e.x - 40, y=self.winfo_y() + e.y - 9, relx=0, rely=0)

    def refresh(self):
        pass


class ValueList(Panel):
    """Rows of 'name  value' - used for Runtime Value Lists, Digital Gauges and settings menus."""

    def __init__(self, app, title, ids, big=False, closable=False):
        super().__init__(app, title, closable)
        self.ids, self.big = ids, big
        self.box = tk.Text(self.body, bg=PANEL, fg=FG, font=('Segoe UI', 16, 'bold') if big else FONT, bd=0,
                           highlightthickness=0, cursor='arrow', wrap='none', spacing1=1)
        self.box.pack(fill='both', expand=True, padx=4, pady=2)
        self.box.bind('<Double-Button-1>', self._edit)
        self.box.bind('<Configure>', lambda e: self.refresh())
        for n, c in enumerate(ROW_COLOURS):
            self.box.tag_config(f'c{n}', foreground=c)
        self.box.tag_config('changed', underline=True)

    def refresh(self):
        t, box = self.app.tune, self.box
        box.config(state='normal')
        box.delete('1.0', 'end')
        box.config(tabs=(max(box.winfo_width() - 8, 60), 'right'))
        n = -1
        for i in self.ids:
            if t is None or str(i) not in t.map or str(i) in pclink.PASSWORD_IDS:
                box.insert('end', '\n')
                n = -1  # PCLink restarts the colour cycle after a gap
                continue
            n += 1
            s = t.get(i)
            name = s['label'].split(' > ')[-1]
            tags = (f'c{n % len(ROW_COLOURS)}',) + (('changed',) if self.app.changed(i) else ())
            box.insert('end', f'{name}\n{fmt(s)}\n' if self.big else f'{name}\t{fmt(s)}\n', tags)
        box.config(state='disabled')

    def _edit(self, e):
        row = int(self.box.index(f'@{e.x},{e.y}').split('.')[0]) - 1
        row = row // 2 if self.big else row
        if row < len(self.ids):
            self.app.edit(self.ids[row])
        return 'break'


class TableView(Panel):
    """Colour graded table grid with axes. Click/drag to select, type a value + Enter, PgUp/PgDn to nudge."""

    def __init__(self, app, tid, closable=False):
        super().__init__(app, app.tune.label(tid).split(' > ')[-1], closable)
        self.tid, self.sel, self.anchor = str(tid), {(0, 0)}, (0, 0)
        self.c = tk.Canvas(self.body, bg=PANEL, highlightthickness=0, takefocus=1)
        self.c.pack(fill='both', expand=True)
        self.c.bind('<Configure>', lambda e: self.refresh())
        self.c.bind('<Button-1>', self._click)
        self.c.bind('<B1-Motion>', lambda e: self._click(e, extend=True))
        self.c.bind('<Shift-Button-1>', lambda e: self._click(e, extend=True))
        self.c.bind('<Double-Button-1>', self._dbl)
        self.c.bind('<Key>', self._key)
        for k, d in (('Up', (-1, 0)), ('Down', (1, 0)), ('Left', (0, -1)), ('Right', (0, 1))):
            self.c.bind(f'<{k}>', lambda e, d=d: self._move(d, False))
            self.c.bind(f'<Shift-{k}>', lambda e, d=d: self._move(d, True))
        self.c.bind('<Prior>', lambda e: self._nudge(1))
        self.c.bind('<Next>', lambda e: self._nudge(-1))
        self.c.bind('<Shift-Prior>', lambda e: self._nudge(10))
        self.c.bind('<Shift-Next>', lambda e: self._nudge(-10))
        self.c.bind('<Control-c>', self._copy)
        self.c.bind('<Control-v>', self._paste)
        self.c.bind('<Control-a>', lambda e: self._select_all())

    def _geom(self):
        s = self.s
        nr, nc = len(s['rows']), len(s['rows'][0])
        x0 = 52 if 'y_axis' in s else 4
        y0 = 36 if 'x_axis' in s else 20
        w, h = self.c.winfo_width(), self.c.winfo_height()
        return nr, nc, x0, y0, max((w - x0 - 2) / nc, 8), max((h - y0 - 2) / nr, 8)

    def refresh(self):
        t, c = self.app.tune, self.c
        c.delete('all')
        if t is None or self.tid not in t.map:
            return
        self.s = s = t.get(self.tid)
        nr, nc, x0, y0, cw, ch = self._geom()
        self.sel = {(r, k) for r, k in self.sel if r < nr and k < nc} or {(0, 0)}
        flat = [v for row in s['rows'] for v in row]
        lo, hi = min(flat), max(flat)
        base = self.app.base_table(self.tid)
        font = ('Segoe UI', max(6, min(9, int(cw / 4.2))))
        c.create_text(4, 2, anchor='nw', fill='#aaaaaa', font=font,
                      text=f'{s["units"] or ""}   X: {s.get("x_axis_parameter", "-")}   Y: {s.get("y_axis_parameter", "-")}')
        for k, v in enumerate(s.get('x_axis', ())[:nc]):
            c.create_text(x0 + (k + .5) * cw, y0 - 9, text=f'{v:g}', fill=FG, font=font)
        for r, v in enumerate(s.get('y_axis', ())[:nr]):
            c.create_text(x0 - 4, y0 + (r + .5) * ch, text=f'{v:g}', fill=FG, font=font, anchor='e')
        for r, row in enumerate(s['rows']):
            for k, v in enumerate(row):
                x, y = x0 + k * cw, y0 + r * ch
                c.create_rectangle(x, y, x + cw, y + ch, fill=heat((v - lo) / (hi - lo) if hi > lo else .5), outline='#202020')
                c.create_text(x + cw / 2, y + ch / 2, text=f'{v:g}', fill='#000000', font=font)
                if base and base[r][k] != v:  # differs from the original tune
                    c.create_rectangle(x + 2, y + 2, x + cw - 2, y + ch - 2, outline='#ffffff', width=2)
        for r, k in self.sel:
            x, y = x0 + k * cw, y0 + r * ch
            c.create_rectangle(x + 1, y + 1, x + cw - 1, y + ch - 1, outline='#000000', width=2, dash=(3, 2))

    def _cell(self, e):
        nr, nc, x0, y0, cw, ch = self._geom()
        return int((e.y - y0) // ch), int((e.x - x0) // cw), nr, nc

    def _click(self, e, extend=False):
        self.c.focus_set()
        r, k, nr, nc = self._cell(e)
        if not (0 <= r < nr and 0 <= k < nc):
            return
        if not extend:
            self.anchor = (r, k)
        self._span((r, k))

    def _span(self, to):
        (r0, k0), (r1, k1) = self.anchor, to
        self.cursor = to
        self.sel = {(r, k) for r in range(min(r0, r1), max(r0, r1) + 1) for k in range(min(k0, k1), max(k0, k1) + 1)}
        self.refresh()

    def _move(self, d, extend):
        nr, nc = len(self.s['rows']), len(self.s['rows'][0])
        r, k = getattr(self, 'cursor', self.anchor)
        to = (min(max(r + d[0], 0), nr - 1), min(max(k + d[1], 0), nc - 1))
        if not extend:
            self.anchor = to
        self._span(to)
        return 'break'

    def _select_all(self):
        self.anchor = (0, 0)
        self._span((len(self.s['rows']) - 1, len(self.s['rows'][0]) - 1))

    def _apply(self, fn):
        rows = [[fn(r, k, v) if (r, k) in self.sel else None for k, v in enumerate(row)] for r, row in enumerate(self.s['rows'])]
        self.app.change(lambda t: t.set_table(self.tid, rows))

    def _nudge(self, n):
        self._apply(lambda r, k, v: v + n * (self.s['step'] or 1))
        return 'break'

    def _key(self, e):
        if e.char and (e.char.isdigit() or e.char in '-.=+*') or e.keysym == 'Return':
            txt = simpledialog.askstring('Set cells', 'Value  (or +n / -n / *n to adjust the selection):',
                                         initialvalue='' if e.keysym == 'Return' else e.char.replace('=', ''), parent=self)
            self.c.focus_set()
            if not txt:
                return
            try:
                if txt[0] in '+*' or (txt[0] == '-' and len(self.sel) > 1):
                    n = float(txt[1:])
                    self._apply({'+': lambda r, k, v: v + n, '-': lambda r, k, v: v - n, '*': lambda r, k, v: v * n}[txt[0]])
                else:
                    n = float(txt)
                    self._apply(lambda r, k, v: n)
            except ValueError as err:
                messagebox.showerror('PCLink', str(err), parent=self)

    def _dbl(self, e):
        """Double-click an axis label to edit that breakpoint."""
        r, k, nr, nc = self._cell(e)
        d = self.app.tune.defs[self.tid]
        ax, idx = ('x', k) if r < 0 <= k < nc else ('y', r) if k < 0 <= r < nr else (None, 0)
        if ax and d[ax] in self.app.tune.map:
            old = self.app.tune.table(d[ax])[0]
            v = simpledialog.askfloat('Axis', f'{ax.upper()} axis value {idx + 1}:', initialvalue=old[idx], parent=self)
            if v is not None:
                row = [None] * len(old)
                row[idx] = v
                self.app.change(lambda t: t.set_table(d[ax], [row]))

    def _copy(self, e):
        rs, ks = sorted({r for r, _ in self.sel}), sorted({k for _, k in self.sel})
        self.clipboard_clear()
        self.clipboard_append('\n'.join('\t'.join(f'{self.s["rows"][r][k]:g}' for k in ks) for r in rs))

    def _paste(self, e):
        r0, k0 = min(self.sel)
        try:
            data = [[float(x) for x in line.split('\t')] for line in self.clipboard_get().strip().splitlines()]
        except (tk.TclError, ValueError):
            return
        rows = [[None] * len(row) for row in self.s['rows']]
        for r, line in enumerate(data):
            for k, v in enumerate(line):
                if r0 + r < len(rows) and k0 + k < len(rows[0]):
                    rows[r0 + r][k0 + k] = v
        self.app.change(lambda t: t.set_table(self.tid, rows))


class App(tk.Tk):
    def __init__(self, tune_path=None, layout_path=None):
        super().__init__()
        self.tune = self.base = None
        self.undo, self.dirty, self.seen, self.floating = [], False, {}, []
        self.geometry('1500x900')
        self.configure(bg=BG)
        ico = os.path.join(pclink.PCLINK_DIR, 'Icon.ico')
        if os.path.exists(ico):
            self.iconbitmap(ico)
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('Treeview', background='#101010', fieldbackground='#101010', foreground=FG, font=FONT, borderwidth=0)
        style.map('Treeview', background=[('selected', SEL)])
        self._menus()

        top = tk.Frame(self, bg=BG, height=24)
        top.pack(fill='x')
        self.tabs = tk.Frame(top, bg=BG)
        self.tabs.pack(side='left', padx=(34, 0))
        self.status = tk.Label(top, text='   PC Log = Off          Offline   ', bg='#ff0000', fg=FG, font=('Segoe UI', 10))
        self.status.pack(side='right', padx=70)
        side = tk.Canvas(self, width=26, bg='#f0f0f0', highlightthickness=0)
        side.pack(side='left', fill='y')
        y = 8
        for name, cmd in (('ECU Settings', self.toggle_tree), ('Log File Manager', None), ('Event Log', None), ('Parameters', None)):
            h = len(name) * 7 + 14
            tag = side.create_text(13, y + h / 2, text=name, angle=90, font=FONT, fill='#000000' if cmd else '#909090')
            if cmd:
                side.tag_bind(tag, '<Button-1>', lambda e, c=cmd: c())
            y += h
        self.desk = tk.Frame(self, bg=BG)
        self.desk.pack(fill='both', expand=True)
        self.desk.bind('<Configure>', lambda e: self._place())
        self._tree_panel()

        self.pages, self.page, self.views = [], None, []
        self.load_layout(layout_path or self._default_layout())
        if tune_path:
            self.open(tune_path)
        self.bind('<Control-o>', lambda e: self.ask_open())
        self.bind('<Control-s>', lambda e: self.save())
        self.bind('<Control-z>', lambda e: self.undo_last())
        self.bind('<F5>', lambda e: self.reload())
        self.protocol('WM_DELETE_WINDOW', self.quit_app)
        self.after(1000, self._watch)

    # ---- chrome
    def _menus(self):
        mb = tk.Menu(self)
        spec = {
            'File': [('Open...', self.ask_open, 'Ctrl+O'), ('Save', self.save, 'Ctrl+S'), ('Save As...', self.save_as, ''),
                     ('Reload from disk', self.reload, 'F5'), None, ('Compare to File...', self.ask_compare, ''),
                     ('Export Settings as JSON...', self.export_json, ''), None, ('Exit', self.quit_app, '')],
            'Options': [('Undo', self.undo_last, 'Ctrl+Z')],
            'ECU Controls': [('Connect', None, 'F3'), ('Store', None, 'F4'), ('Lock/Unlock ECU...', None, ''), ('Update Firmware...', None, '')],
            'Display Mode': [],
            'Layout': [('Open Layout...', self.ask_layout, '')],
            'View': [('ECU Settings', self.toggle_tree, 'F12'), ('Find Setting...', self.focus_search, 'Ctrl+F')],
            'Logging': [('PC Logging', None, 'F8'), ('ECU Logging Setup...', None, ''), ('Open Log File...', None, '')],
            'Tuning': [('Mixture Map...', None, ''), ('Quick Tune', None, '')],
            'Help': [('PCLink Help', self.help, 'F1'), ('About', self.about, '')],
        }
        for name, items in spec.items():
            m = tk.Menu(mb, tearoff=0)
            for it in items:
                if it is None:
                    m.add_separator()
                else:  # entries without a command need a live ECU / log data and are shown disabled
                    m.add_command(label=it[0], command=it[1], accelerator=it[2], state='normal' if it[1] else 'disabled')
            mb.add_cascade(label=name, menu=m)
            if name == 'Layout':
                self.layout_menu = m
        self.config(menu=mb)
        self.bind('<F1>', lambda e: self.help())
        self.bind('<F12>', lambda e: self.toggle_tree())
        self.bind('<Control-f>', lambda e: self.focus_search())

    def _tree_panel(self):
        self.tree_frame = f = tk.Frame(self.desk, bg='#101010', highlightbackground=BAR, highlightthickness=1)
        tk.Label(f, text='ECU Settings', bg=BAR, fg=FG, font=FONT, anchor='w').pack(fill='x')
        self.search = tk.StringVar()
        e = tk.Entry(f, textvariable=self.search, bg='#202020', fg=FG, insertbackground=FG, font=FONT, bd=0)
        e.pack(fill='x', padx=2, pady=2)
        self.search_entry = e
        self.search.trace_add('write', lambda *a: self._fill_tree())
        self.tree = ttk.Treeview(f, show='tree')
        sb = ttk.Scrollbar(f, command=self.tree.yview)
        self.tree.config(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<Double-Button-1>', self._tree_open)
        self.tree.bind('<Return>', self._tree_open)
        self.tree_shown = False

    def toggle_tree(self):
        self.tree_shown = not self.tree_shown
        if self.tree_shown:
            self.tree_frame.place(x=0, y=0, width=360, relheight=1)
            self.tree_frame.lift()
        else:
            self.tree_frame.place_forget()

    def focus_search(self):
        if not self.tree_shown:
            self.toggle_tree()
        self.search_entry.focus_set()

    def _fill_tree(self):
        tr, t = self.tree, self.tune
        tr.delete(*tr.get_children())
        if t is None:
            return
        words, nodes = self.search.get().lower().split(), {}
        for i, e in t.map.items():
            d = t.defs[i]
            if i in pclink.PASSWORD_IDS or e.get('ReadOnly') == 'true' or not d['visible'] or not d['path']:
                continue
            if words and not all(w in (t.label(i) + ' ' + d['name']).lower() for w in words):
                continue
            parent, path = '', ()
            for part in d['path'].split(' > '):
                path += (part,)
                if path not in nodes:
                    nodes[path] = tr.insert(parent, 'end', text=part, open=bool(words))
                parent = nodes[path]
            mark = '* ' if self.changed(i) else ''
            tr.insert(parent, 'end', iid=f'id{i}', text=f'{mark}{d["caption"]}:  {fmt(t.get(i))}')

    def _tree_open(self, e):
        iid = self.tree.focus()
        if iid.startswith('id'):
            self.edit(iid[2:])
            return 'break'

    # ---- layout
    def _default_layout(self):
        try:  # the layout PCLink itself last used
            for el in ET.parse(OPTIONS_XML).iter():
                for k, p in el.attrib.items():
                    if k.endswith('LayoutFile') and os.path.exists(p):
                        return p
        except (OSError, ET.ParseError):
            pass
        return os.path.join(pclink.PCLINK_DIR, 'Layouts', 'DefaultLayout.llf5')

    def ask_layout(self):
        p = filedialog.askopenfilename(initialdir=os.path.join(pclink.PCLINK_DIR, 'Layouts'),
                                       filetypes=[('PCLink layout', '*.llf5 *.llfx')])
        if p:
            self.load_layout(p)

    def load_layout(self, path):
        root = ET.parse(path).getroot()
        self.pages = [(p.get('Name'), list(p.iter('View'))) for p in root.iter('Page')]
        for w in self.tabs.winfo_children():
            w.destroy()
        for name, _ in self.pages:
            b = tk.Label(self.tabs, text=f'  {name}  ', bg=BG, fg=FG, font=('Segoe UI', 10), cursor='hand2')
            b.pack(side='left')
            b.bind('<Button-1>', lambda e, n=name: self.show_page(n))
        sel = root.find('.//Pages').get('SelectedPage') if root.find('.//Pages') is not None else None
        self.show_page(sel if sel in [n for n, _ in self.pages] else self.pages[0][0])

    def show_page(self, name):
        self.page = name
        for b in self.tabs.winfo_children():
            b.config(bg=SEL if b.cget('text').strip() == name else BG)
        for v, _ in self.views:
            v.destroy()
        self.views = []
        for el in dict(self.pages)[name]:
            v = self._make_view(el)
            self.views.append((v, tuple(int(el.get(k)) for k in ('Left', 'Top', 'Width', 'Height'))))
        self._place()
        self.refresh()

    def _node_ids(self, name):
        """Editable settings under the ECU Settings menu node called `name`."""
        t = self.tune
        return [i for i in t.map if name in t.defs[i]['path'].split(' > ') and i not in pclink.PASSWORD_IDS
                and t.defs[i]['visible'] and t.map[i].get('ReadOnly') != 'true'] if t else []

    def _make_view(self, el):
        kind, lang = el.get('Type'), pclink.load_strings()
        ids = [i for g in el.iter('RuntimeViewDataIDGroup') for i in g.get('DataIDs').split(',') if i]
        if kind == 'Auto Settings':
            name = lang.get(el.get('BaseCaption'), '')
            node = self._node_ids(name)
            tables = [i for i in node if self.tune.map[i].get('Type') == '1' and self.tune.defs[i]['caption'] == name]
            if tables:
                return TableView(self, tables[0])
            if node:
                return ValueList(self, name, node)
            kind = 'ECU Settings'
        if kind in ('Runtime Value List', 'Digital Gauge'):
            return ValueList(self, el.get('Caption') or '', ids, big=kind == 'Digital Gauge')
        note = {'ECU Settings': 'Open ECU Settings on the left edge (F12) to browse and edit every setting',
                'Help Browser': 'Press F1 for the PCLink help'}.get(kind, LIVE_ONLY)
        p = Panel(self, el.get('Caption') or el.get('ViewCaption') or kind)  # gauges, plots, mixture map, help browser
        tk.Label(p.body, text=f'{kind}\n{note}', bg=PANEL, fg='#606060', font=FONT, wraplength=220).pack(expand=True)
        return p

    def _place(self):
        if not self.views:
            return
        w = max(max(x + cw for _, (x, y, cw, ch) in self.views), 1200)
        h = max(max(y + ch for _, (x, y, cw, ch) in self.views), 700)
        sx, sy = self.desk.winfo_width() / w, self.desk.winfo_height() / h
        for v, (x, y, cw, ch) in self.views:
            v.place(x=x * sx, y=y * sy, width=cw * sx, height=ch * sy)
        for f in self.floating:
            if f.winfo_exists():
                f.lift()
        if self.tree_shown:
            self.tree_frame.lift()

    # ---- tune
    def ask_open(self):
        p = filedialog.askopenfilename(filetypes=[('PCLink tune', '*.pclx *.pcl5'), ('All files', '*.*')],
                                       initialdir=os.path.dirname(self.tune.path) if self.tune else pclink.PCLINK_DIR)
        if p and self._discard_ok():
            self.open(p)

    def open(self, path, base=None):
        try:
            tune = Tune(path)
        except (ValueError, PermissionError, OSError, ET.ParseError) as err:
            return messagebox.showerror('PCLink', f'{path}\n\n{err}')
        self.tune, self.undo, self.dirty = tune, [], False
        self.seen = {path: os.path.getmtime(path)}
        stem, ext = os.path.splitext(path)
        orig = base or (stem[:-3] + ext if pclink.is_ai_copy(path) else None)
        self.base = None
        if orig and os.path.exists(orig) and os.path.abspath(orig) != os.path.abspath(path):
            try:
                self.base = Tune(orig)
            except (ValueError, PermissionError, OSError, ET.ParseError):
                pass
        self.show_page(self.page)
        self._fill_tree()
        self._title()

    def ask_compare(self):
        p = filedialog.askopenfilename(filetypes=[('PCLink tune', '*.pclx *.pcl5')])
        if p and self.tune:
            try:
                self.base = Tune(p)
            except (ValueError, PermissionError, OSError, ET.ParseError) as err:
                return messagebox.showerror('PCLink', str(err))
            n = sum(self.changed(i) for i in self.tune.map)
            self.refresh()
            self._fill_tree()
            messagebox.showinfo('Compare', f'{n} settings differ from\n{p}\n\nThey are outlined in tables and marked * in ECU Settings.')

    def _title(self):
        t = self.tune
        self.title('PCLink Engine Management' + (f' - {t.path}{" *" if self.dirty else ""}' if t else ''))

    def changed(self, i):
        b, i = self.base, str(i)
        if b is None or i not in b.map or i not in self.tune.map:
            return False
        return ET.tostring(b.map[i]) != ET.tostring(self.tune.map[i])

    def base_table(self, i):
        return self.base.table(i) if self.base and str(i) in self.base.map and self.changed(i) else None

    def refresh(self):
        for v, _ in self.views:
            v.refresh()
        self.floating = [f for f in self.floating if f.winfo_exists()]
        for f in self.floating:
            f.refresh()

    def change(self, fn):
        """Run an edit on the tune with undo, validation errors and redraw."""
        before = self.tune.text
        try:
            fn(self.tune)
        except (ValueError, KeyError) as err:
            self.tune.load_text(before)
            return messagebox.showerror('PCLink', str(err.args[0] if err.args else err))
        self.undo.append(before)
        self.dirty = True
        self.refresh()
        self._fill_tree()
        self._title()

    def undo_last(self):
        if self.undo:
            self.tune.load_text(self.undo.pop())
            self.dirty = bool(self.undo)
            self.refresh()
            self._fill_tree()
            self._title()

    def edit(self, i):
        t, i = self.tune, str(i)
        if t is None or i not in t.map:
            return
        s = t.get(i)
        if s['kind'] == 'table':
            p = TableView(self, i, closable=True)
            p.place(relx=.22, rely=.08, relwidth=.62, relheight=.62)
            self.floating.append(p)
            p.refresh()
            return p.c.focus_set()
        if s['read_only']:
            return messagebox.showinfo('PCLink', f'{s["label"]}\n\n{fmt(s)}\n\nRuntime value - read only.')
        if s['kind'] == 'option':
            v = self._choose(s)
        else:
            rng = f'  ({s["min"]:g} .. {s["max"]:g})' if s['min'] is not None and s['max'] is not None else ''
            v = simpledialog.askstring(s['label'].split(' > ')[-1], f'{s["label"]}\n{s["units"] or ""}{rng}',
                                       initialvalue=f'{s["value"]:g}' if isinstance(s['value'], float) else s['value'], parent=self)
        if v is not None and v != '':
            self.change(lambda t: t.set(i, v))

    def _choose(self, s):
        win = tk.Toplevel(self)
        win.title(s['label'].split(' > ')[-1])
        win.transient(self)
        tk.Label(win, text=s['label'], font=FONT).pack(padx=10, pady=6)
        lb = tk.Listbox(win, height=min(len(s['options']), 22), width=44, font=FONT, exportselection=False)
        for o in s['options']:
            lb.insert('end', o)
        lb.selection_set(s['value'])
        lb.see(s['value'])
        lb.pack(padx=10, fill='both', expand=True)
        out = []
        ok = lambda e=None: (out.append(lb.curselection()[0]) if lb.curselection() else None, win.destroy())
        lb.bind('<Double-Button-1>', ok)
        lb.bind('<Return>', ok)
        tk.Button(win, text='OK', width=10, command=ok).pack(pady=6)
        lb.focus_set()
        win.grab_set()
        self.wait_window(win)
        return out[0] if out else None

    def save(self, path=None):
        if self.tune is None:
            return
        try:
            p = self.tune.save(path)
        except (ValueError, OSError) as err:
            return messagebox.showerror('PCLink', str(err))
        self.dirty, self.seen = False, {p: os.path.getmtime(p)}
        self._title()

    def save_as(self):
        if self.tune:
            ext = os.path.splitext(self.tune.path)[1]
            p = filedialog.asksaveasfilename(defaultextension=ext, filetypes=[('PCLink tune', f'*{ext}')],
                                             initialfile=os.path.basename(pclink.out_path(self.tune.path)))
            if p:
                self.save(p)

    def export_json(self):
        if self.tune:
            p = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON', '*.json')])
            if p:
                pclink.main(['dump', self.tune.path, p])

    def reload(self):
        if self.tune and self._discard_ok():
            self.open(self.tune.path)

    def _discard_ok(self):
        return not self.dirty or messagebox.askyesno('PCLink', 'Discard unsaved changes?')

    def _watch(self):
        """Follow edits made outside this window (the AI workflow)."""
        t = self.tune
        if t and not self.dirty:
            ai = pclink.out_path(t.path)
            for p in (ai, t.path):
                if os.path.exists(p) and os.path.getmtime(p) > self.seen.get(p, 0 if p == t.path else self.seen.get(t.path, 0)):
                    self.open(p)
                    break
        self.after(1000, self._watch)

    def help(self):
        chm = os.path.join(pclink.PCLINK_DIR, 'Help_File_ENG.chm')
        os.startfile(chm) if os.path.exists(chm) else messagebox.showinfo('PCLink', 'Help file not found.')

    def about(self):
        m = self.tune.memory if self.tune else {}
        messagebox.showinfo('About', 'Offline PCLink look-alike for viewing and editing tune files.\n'
                                     'Not made by or affiliated with Link Engine Management.\n\n'
                            + '\n'.join(f'{k}: {v}' for k, v in m.items() if v))

    def quit_app(self):
        if self._discard_ok():
            self.destroy()


if __name__ == '__main__':
    App(*sys.argv[1:3]).mainloop()
