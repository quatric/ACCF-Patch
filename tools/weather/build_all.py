#!/usr/bin/env python3
"""Build the weather patch for every City Folk revision.

  build_all.py --dols <dir of <REV>.dol> --donor <Mario & Sonic main.dol> --out <dir>

Writes <out>/<REV>/main.weather.dol, <out>/riivolution/<REV>-weather.xml and weather_patches.json
(next to this script) for the patcher.  weather_patches.json holds the Mario & Sonic FCD machine code the
patch is made of: it is generated locally from your own copy of the game and is never committed.
"""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_patch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dols", required=True)
    ap.add_argument("--donor", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", help="comma list of revisions")
    a = ap.parse_args()
    ref = os.path.join(a.dols, "RUUE02.dol")
    keys = a.only.split(",") if a.only else list(build_patch.REVS)
    allp = {}
    os.makedirs(os.path.join(a.out, "riivolution"), exist_ok=True)
    for rev in keys:
        out = os.path.join(a.out, rev)
        info = build_patch.build_rev(rev, os.path.join(a.dols, rev + ".dol"), ref, a.donor, out)
        os.replace(os.path.join(out, rev + "-weather.xml"), os.path.join(a.out, "riivolution", rev + "-weather.xml"))
        allp[rev] = {"base": info["base"], "blob": info["blob"],
                     "patches": info["patches"]}
    json.dump(allp, open(os.path.join(HERE, "weather_patches.json"), "w"))
    print("wrote weather_patches.json (%d revisions)" % len(allp))


if __name__ == "__main__":
    main()
