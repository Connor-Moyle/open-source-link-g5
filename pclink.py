"""Read and modify Link ECU PCLink tune files (.pclx / .pcl5) without the GUI.

A tune file is XML ("LinkStorage") wrapped in XXTEA: 3 header words
[random nonce, payload length, 0] followed by the XML, zero padded.
Setting names, units, limits and option lists come from PCLink's own
ECU.cfgr / Languages.cfgr, and the cipher keys from PCLink.exe - all read
from the user's own install at runtime; none of it is shipped here.

CLI:  python pclink.py --help          API:  from pclink import Tune
"""
import argparse, functools, json, os, re, struct, sys, tempfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

PCLINK_DIR = os.environ.get('PCLINK_DIR', r'C:\Link G5\PCLink G5')
PASSWORD_IDS = {'2294', '2295', '2303', '2324'}  # tuner password data: never shown, never edited
M, DELTA = 0xffffffff, 0x9e3779b9


# ---------------------------------------------------------------- codec

@functools.lru_cache(None)
def _keys():
    """(tune key, language key), read out of the user's own PCLink.exe - no key material ships with this tool."""
    with open(os.path.join(PCLINK_DIR, 'PCLink.exe'), 'rb') as f:
        b = f.read()
    pe = struct.unpack_from('<I', b, 0x3c)[0]
    nsec, optsz = struct.unpack_from('<H', b, pe + 6)[0], struct.unpack_from('<H', b, pe + 20)[0]
    base = struct.unpack_from('<I', b, pe + 24 + 28)[0]
    secs = [struct.unpack_from('<4I', b, pe + 24 + optsz + 40 * i + 8) for i in range(nsec)]  # vsize, va, rawsize, rawptr

    def off(va):
        for vsize, v, rawsize, rawptr in secs:
            if v <= va - base < v + max(vsize, rawsize):
                return va - base - v + rawptr
        raise ValueError('unsupported PCLink.exe version (key table not found)')

    d = b.find(struct.pack('<I', DELTA))             # the XXTEA routine ...
    m = b.rfind(bytes([0x8a, 0x9a]), max(d - 0x200, 0), d)  # ... follows a routine that indexes the key table
    if d < 0 or m < 0:
        raise ValueError('unsupported PCLink.exe version (cipher not found)')
    t = off(struct.unpack_from('<I', b, m + 2)[0] + 0x24)
    return struct.unpack_from('<4I', b, t), struct.unpack_from('<4I', b, t + 16)


def _mx(z, y, s, p, e, k):
    return ((((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))) ^ ((s ^ y) + (k[(p & 3) ^ e] ^ z))) & M


def decode(raw, key=None):
    """File bytes -> (payload bytes, nonce)."""
    key = key or _keys()[0]
    if len(raw) < 16 or len(raw) % 4:
        raise ValueError('not a PCLink file (bad length)')
    n = len(raw) // 4
    v = list(struct.unpack(f'<{n}I', raw))
    s, y = ((6 + 52 // n) * DELTA) & M, v[0]
    while s:
        e = (s >> 2) & 3
        for p in range(n - 1, 0, -1):
            v[p] = y = (v[p] - _mx(v[p - 1], y, s, p, e, key)) & M
        v[0] = y = (v[0] - _mx(v[n - 1], y, s, 0, e, key)) & M
        s = (s - DELTA) & M
    if v[2] != 0 or not len(raw) - 16 <= v[1] <= len(raw) - 12:
        raise ValueError('not a PCLink file this tool can read (wrong type, or saved with "Save as Encrypted")')
    return struct.pack(f'<{n}I', *v)[12:12 + v[1]], v[0]


def encode(payload, key=None, nonce=None):
    """Payload bytes -> file bytes, laid out exactly as PCLink writes them."""
    key = key or _keys()[0]
    n = len(payload) // 4 + 4
    if nonce is None:
        nonce = struct.unpack('<I', os.urandom(4))[0]
    buf = (struct.pack('<3I', nonce, len(payload), 0) + payload).ljust(n * 4, b'\0')
    v = list(struct.unpack(f'<{n}I', buf))
    s, z = 0, v[n - 1]
    for _ in range(6 + 52 // n):
        s = (s + DELTA) & M
        e = (s >> 2) & 3
        for p in range(n - 1):
            v[p] = z = (v[p] + _mx(z, v[p + 1], s, p, e, key)) & M
        v[n - 1] = z = (v[n - 1] + _mx(z, v[0], s, n - 1, e, key)) & M
    return struct.pack(f'<{n}I', *v)


# ---------------------------------------------------------------- definitions

def load_defs():
    """{DataId: {name, caption, path, units, min, max, options, x, y, xparam, yparam, visible}}"""
    return _definitions()['defs']


def load_strings():
    """{string id: English text} - PCLink's language table."""
    return _definitions()['lang']


def _definitions():
    src = os.path.join(PCLINK_DIR, 'ECU.cfgr')
    cache = os.path.join(tempfile.gettempdir(), 'pclink_defs_cache.json')
    stamp = os.path.getmtime(src)
    if os.path.exists(cache):
        with open(cache, encoding='utf-8') as f:
            c = json.load(f)
        if c.get('stamp') == stamp and 'lang' in c:
            return c

    lang = {}
    with open(os.path.join(PCLINK_DIR, 'Languages.cfgr'), 'rb') as f:
        for line in decode(f.read(), _keys()[1])[0].decode('utf-16').splitlines():
            a = line.split(',', 2)
            if len(a) == 3:
                lang[a[0]] = a[2]
    with open(src, 'rb') as f:
        root = ET.fromstring(decode(f.read())[0])
    own = {p.get('DataId'): (p.get('Name'), {x.get('Name'): x.get('Value') for x in p.iter('Property')})
           for p in root.find('Parameters')}

    def props(i, seen=()):  # own properties override the ones inherited through CopyFromID
        p = own[i][1]
        base = p.get('CopyFromID')
        return {**props(base, seen + (i,)), **p} if base in own and base not in seen else p

    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    defs = {}
    for i, (name, _) in own.items():
        p = props(i)
        path = (p.get('Parent') or '').split('\\&')[0].split('\\_')
        defs[i] = {
            'name': name,
            'caption': lang.get(p.get('Caption'), name),
            'path': ' > '.join(lang.get(x, x) for x in path if x),
            'units': p.get('Units'), 'min': num(p.get('Min')), 'max': num(p.get('Max')),
            'options': [lang.get(x, x) for x in p['Options'].rstrip(',').split(',')] if p.get('Options') else None,
            'x': p.get('xLabels'), 'y': p.get('yLabels'),
            'xparam': p.get('XAxisParameterID'), 'yparam': p.get('YAxisParameterID'),
            'visible': p.get('Visible') != 'false',
        }
    c = {'stamp': stamp, 'defs': defs, 'lang': lang}
    with open(cache, 'w', encoding='utf-8') as f:
        json.dump(c, f)
    return c


# ---------------------------------------------------------------- tune

KIND = {'0': 'number', '1': 'table', '3': 'option', '4': 'runtime', '5': 'runtime', '8': 'text', '9': 'parameter'}


class Tune:
    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            payload, _ = decode(f.read())
        self.defs = load_defs()
        self.load_text(payload.decode('latin-1'))

    def load_text(self, text):
        """Replace the whole tune content (used for undo)."""
        self.text = text  # edits are done on the text so untouched bytes stay identical
        root = ET.fromstring(text)
        self.memory = {e.tag: e.get('Value') for e in root.find('Memory')}
        self.map = {e.get('DataId'): e for e in root.find('Map')}
        if self.map.get('2303') is not None and self.map['2303'].get('Value') != '0':
            raise PermissionError('this tune is password protected - unlock it in PCLink first')

    def _el(self, i, write=False):
        i = str(i)
        if i not in self.map or i in PASSWORD_IDS:
            raise KeyError(f'no setting with DataId {i} in this tune')
        e = self.map[i]
        if write and e.get('ReadOnly') == 'true':
            raise ValueError(f'{i} ({self.defs[i]["name"]}) is a read-only runtime value')
        return i, e

    def label(self, i):
        d = self.defs[str(i)]
        return f'{d["path"]} > {d["caption"]}' if d['path'] else d['caption']

    def table(self, i):
        """Table values as a list of rows of floats."""
        i, e = self._el(i)
        return [[float(x) for x in r.get('Value').split(',')] for r in e]

    def get(self, i):
        """Everything known about one setting, as a plain dict."""
        i, e = self._el(i)
        d = self.defs[i]
        out = {'id': int(i), 'label': self.label(i), 'name': d['name'], 'kind': KIND.get(e.get('Type'), e.get('Type')),
               'units': d['units'], 'min': d['min'], 'max': d['max'], 'step': float(e.get('Multi')) or None,
               'read_only': e.get('ReadOnly') == 'true'}
        v = e.get('Value')
        if out['kind'] == 'table':
            out['rows'] = self.table(i)
            for ax in 'xy':
                if d[ax] in self.map:
                    out[ax + '_axis'] = self.table(d[ax])[0]
                ref = self.map.get(d[ax + 'param'])
                if ref is not None and ref.get('Value') in self.defs:
                    out[ax + '_axis_parameter'] = self.defs[ref.get('Value')]['caption']
        elif out['kind'] == 'option':
            out['value'] = int(v)
            opts = d['options'] or []
            out['value_label'] = opts[int(v)] if int(v) < len(opts) else None
            out['options'] = opts
        elif out['kind'] == 'parameter':
            out['value'] = int(v)
            out['value_label'] = self.defs[v]['caption'] if v in self.defs else None
        elif out['kind'] == 'text':
            out['value'] = v
        else:
            out['value'] = float(v)
            if d['options'] and out['value'] == int(out['value']) and 0 <= int(out['value']) < len(d['options']):
                out['value_label'] = d['options'][int(out['value'])]  # runtime status text
        return out

    def find(self, text):
        """DataIds whose label or internal name contains every word of text."""
        words = text.lower().split()
        return [i for i in self.map if i not in PASSWORD_IDS
                and all(w in (self.label(i) + ' ' + self.defs[i]['name']).lower() for w in words)]

    def _num(self, i, e, value):
        d, v, step = self.defs[i], float(value), float(e.get('Multi'))
        if (d['min'] is not None and v < d['min']) or (d['max'] is not None and v > d['max']):
            raise ValueError(f'{value} is outside {d["min"]}..{d["max"]} for {i} ({self.label(i)})')
        if step <= 0:
            return str(int(v)) if v == int(v) else repr(v)
        v = round(v / step) * step  # the ECU only stores multiples of the step
        dec = max(0, len(f'{step:.4f}'.rstrip('0').split('.')[1]))
        return f'{v:.{dec}f}'

    def set(self, i, value):
        """Set a number / option (index or label) / text / parameter setting."""
        i, e = self._el(i, write=True)
        kind = KIND.get(e.get('Type'))
        if kind == 'table':
            raise ValueError(f'{i} is a table - use set_cell or set_table')
        if kind == 'option':
            opts = [o.lower() for o in self.defs[i]['options'] or []]
            s = str(value).strip().lower()
            idx = int(s) if s.lstrip('-').isdigit() else opts.index(s) if s in opts else None
            if idx is None or not 0 <= idx < int(e.get('Count')):
                raise ValueError(f'{value!r} is not an option of {i}: {self.defs[i]["options"]}')
            new = str(idx)
        elif kind == 'text':
            new = str(value)
            if len(new) > int(e.get('Count')) or not new.isascii():
                raise ValueError(f'text for {i} must be ASCII and at most {e.get("Count")} characters')
        elif kind == 'parameter':
            new = str(int(value))
            if new != '0' and new not in self.defs:
                raise ValueError(f'{value} is not a known parameter DataId')
        else:
            new = self._num(i, e, value)
        pat = re.compile(r'(<D%s [^>]*?\bValue=")[^"]*' % i)
        self.text, n = pat.subn(lambda m: m.group(1) + escape(new, {'"': '&quot;'}), self.text, count=1)
        assert n == 1, i
        e.set('Value', new)

    def set_table(self, i, rows):
        """Replace table cells. rows: list of rows; None keeps a row or cell as it is."""
        i, e = self._el(i, write=True)
        if KIND.get(e.get('Type')) != 'table':
            raise ValueError(f'{i} is not a table')
        block = re.search(r'<D%s .*?</D%s>' % (i, i), self.text, re.S)
        body, old = block.group(), list(e)
        if len(rows) > len(old):
            raise ValueError(f'{i} has {len(old)} rows, got {len(rows)}')
        for r, row in enumerate(rows):
            if row is None:
                continue
            cells = old[r].get('Value').split(',')
            if len(row) != len(cells):
                raise ValueError(f'{i} has {len(cells)} columns, row {r} has {len(row)}')
            new = ','.join(c if x is None else self._num(i, e, x) for c, x in zip(cells, row))
            body, n = re.subn(r'(<Row%d Value=")[^"]*' % r, lambda m: m.group(1) + new, body, count=1)
            assert n == 1, (i, r)
            old[r].set('Value', new)
        self.text = self.text[:block.start()] + body + self.text[block.end():]

    def set_cell(self, i, row, col, value):
        rows = [None] * (row + 1)
        rows[row] = [None] * len(self.table(i)[row])
        rows[row][col] = value
        self.set_table(i, rows)

    def save(self, path=None):
        """Write the tune. Only ever overwrites its own *.ai.* copies, never another existing file."""
        path = path or out_path(self.path)
        if os.path.exists(path) and not is_ai_copy(path):
            raise ValueError(f'refusing to overwrite existing file {path} - save to a new name')
        ET.fromstring(self.text)  # must still be well-formed
        with open(path, 'wb') as f:
            f.write(encode(self.text.encode('latin-1')))
        self.path = path
        return path


def is_ai_copy(path):
    return os.path.splitext(path)[0].endswith('.ai')


def out_path(path):
    stem, ext = os.path.splitext(path)
    return path if is_ai_copy(path) else f'{stem}.ai{ext}'


# ---------------------------------------------------------------- CLI

def show(s):
    if s['kind'] != 'table':
        v = s['value_label'] if s.get('value_label') is not None else s['value']
        return f'{s["id"]:>5}  {s["label"]} = {v} {s["units"] or ""}'.rstrip()
    out = [f'{s["id"]:>5}  {s["label"]}  ({len(s["rows"])} x {len(s["rows"][0])}, {s["units"] or "no units"})'
           f'  X: {s.get("x_axis_parameter", "-")}  Y: {s.get("y_axis_parameter", "-")}']
    if 'x_axis' in s:
        out.append('        ' + ' '.join(f'{x:>7g}' for x in s['x_axis']))
    for r, row in enumerate(s['rows']):
        y = f'{s["y_axis"][r]:>7g}' if r < len(s.get('y_axis', ())) else f'{"r" + str(r):>7}'
        out.append(y + ' ' + ' '.join(f'{x:>7g}' for x in row))
    return '\n'.join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('info', help='ECU / firmware details of a tune'); a.add_argument('tune')
    a = sub.add_parser('find', help='search settings by name'); a.add_argument('tune'); a.add_argument('text', nargs='+')
    a = sub.add_parser('get', help='show one setting or table'); a.add_argument('tune'); a.add_argument('id')
    a.add_argument('--json', action='store_true')
    a = sub.add_parser('set', help='change a setting; writes <name>.ai.pclx unless -o is given')
    a.add_argument('tune'); a.add_argument('id'); a.add_argument('value')
    a.add_argument('--cell', nargs=2, type=int, metavar=('ROW', 'COL'), help='table cell (0-based)')
    a.add_argument('-o', '--out')
    a = sub.add_parser('dump', help='all editable settings as JSON'); a.add_argument('tune'); a.add_argument('out', nargs='?')
    a = sub.add_parser('decode', help='tune -> raw XML'); a.add_argument('tune'); a.add_argument('out')
    a = sub.add_parser('encode', help='raw XML -> tune'); a.add_argument('xml'); a.add_argument('out')
    args = ap.parse_args(argv)

    if args.cmd == 'decode':
        t = Tune(args.tune)  # goes through Tune so password protected files are refused
        with open(args.out, 'wb') as f:
            f.write(t.text.encode('latin-1'))
        return
    if args.cmd == 'encode':
        with open(args.xml, 'rb') as f:
            xml = f.read()
        ET.fromstring(xml)
        with open(args.out, 'wb') as f:
            f.write(encode(xml))
        return

    t = Tune(args.tune)
    if args.cmd == 'info':
        print(json.dumps({**t.memory, 'settings': len(t.map)}, indent=2))
    elif args.cmd == 'find':
        for i in t.find(' '.join(args.text)):
            s = t.get(i)
            print(show(s).split('\n')[0] + ('' if s['kind'] != 'runtime' else '  [runtime]'))
    elif args.cmd == 'get':
        s = t.get(args.id)
        print(json.dumps(s, indent=2) if args.json else show(s))
    elif args.cmd == 'set':
        before = show(t.get(args.id)).split('\n')[0]
        if args.cell:
            before = f'{args.id} [{args.cell[0]},{args.cell[1]}] = {t.table(args.id)[args.cell[0]][args.cell[1]]}'
            t.set_cell(args.id, args.cell[0], args.cell[1], args.value)
            after = t.table(args.id)[args.cell[0]][args.cell[1]]
        else:
            t.set(args.id, args.value)
            after = show(t.get(args.id)).split('\n')[0]
        print(f'was: {before}\nnow: {after}\nsaved: {t.save(args.out)}')
    elif args.cmd == 'dump':
        data = {'ecu': t.memory, 'settings': [t.get(i) for i in t.map
                                              if i not in PASSWORD_IDS and t.map[i].get('ReadOnly') != 'true']}
        if args.out:
            with open(args.out, 'w', encoding='utf-8') as f:
                json.dump(data, f)
            print(f'{len(data["settings"])} settings -> {args.out}')
        else:
            json.dump(data, sys.stdout)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, PermissionError, FileNotFoundError) as err:
        sys.exit(f'error: {err.args[0] if err.args else err}')
