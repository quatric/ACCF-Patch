"""Add the Forecast Channel weather patch to a City Folk main.dol (for the patcher).

The bundled patch data contains both boot modes. build_all.py regenerates it
from the reference discs; available() checks whether the data is installed.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'gcpad'))
import patch_dol


def path(root=HERE):
    return os.path.join(root, 'weather_patches.json')


def available(root=HERE):
    return os.path.exists(path(root))


MODES = ('disable_with_b', 'enable_with_b')


def apply(data, rev, root=HERE, mode='disable_with_b'):
    if mode not in MODES:
        raise ValueError('unknown weather boot mode: %s' % mode)
    with open(path(root)) as source:
        p = json.load(source)[rev]
    if mode == 'enable_with_b':
        if 'enable_with_b' not in p:
            raise RuntimeError('weather data does not include the hold-B-to-enable mode; regenerate it')
        p = p['enable_with_b']
    dol = patch_dol.Dol(data)
    for w in p['patches']:
        fo = dol.v2f(w['address'])
        old = bytes.fromhex(w['old'])
        if fo is None or bytes(dol.d[fo:fo + len(old)]) != old:
            raise RuntimeError('weather hook site 0x%08X is not stock; already patched, or another build' % w['address'])
    for w in p['patches']:
        new = bytes.fromhex(w['bytes'])
        fo = dol.v2f(w['address'])
        dol.d[fo:fo + len(new)] = new
    dol.add_text(p['base'], bytes.fromhex(p['blob']))
    return bytes(dol.d)
