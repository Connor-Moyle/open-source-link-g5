"""Self-check against the real test tune.  Run:  python test_pclink.py"""
import os, tempfile
import pclink

TUNE = os.path.join(pclink.PCLINK_DIR, 'Use me as a test tune', 'BMW E30.pclx')
FUEL = 2365  # Fuel Table 1

raw = open(TUNE, 'rb').read()
payload, nonce = pclink.decode(raw)
assert payload.startswith(b'<?xml') and payload.rstrip().endswith(b'</LinkStorage>')
assert pclink.encode(payload, nonce=nonce) == raw, 'encoder is not byte-identical to PCLink'

t = pclink.Tune(TUNE)
original = t.text
assert t.get(FUEL)['label'].endswith('Fuel Table 1') and len(t.table(FUEL)) == 20
assert str(FUEL) in t.find('fuel table 1')

old = t.table(FUEL)[3][4]
t.set_cell(FUEL, 3, 4, old + 1.04)  # snaps to the 0.1 step
out = os.path.join(tempfile.mkdtemp(), 'edited.pclx')
t.save(out)
t2 = pclink.Tune(out)
assert abs(t2.table(FUEL)[3][4] - (old + 1.0)) < 1e-9
a, b = original.split('\n'), t2.text.split('\n')
assert len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1, 'edit touched more than one line'

for bad in (lambda: t.set_cell(FUEL, 0, 0, 9999),          # above Max
            lambda: t.set(20, 1),                          # read-only runtime value
            lambda: t.get(2294),                           # password data stays hidden
            lambda: t.save(TUNE)):                         # original is never overwritten
    try:
        bad()
    except (ValueError, KeyError):
        continue
    raise AssertionError('guard did not fire')
assert open(TUNE, 'rb').read() == raw
print('ok')
