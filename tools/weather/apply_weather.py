"""Add the Forecast Channel weather patch to a City Folk main.dol (for the patcher).

The patch data (weather_patches.json) is made by build_all.py from your own Mario & Sonic disc, so it
exists only on machines where you ran that.  available() says whether it does.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'gcpad'))
import patch_dol


def path(root=HERE):
    return os.path.join(root, 'weather_patches.json')


def available(root=HERE):
    return os.path.exists(path(root))


def apply(data, rev, root=HERE):
    p = json.load(open(path(root)))[rev]
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
