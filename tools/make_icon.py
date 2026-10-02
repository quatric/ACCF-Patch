#!/usr/bin/env python3
"""Build the app icon from assets/logo.png (the Animal Crossing: City Folk logo).

The logo is padded to a transparent square, then written out as:
  assets/icon.png   (1024x1024)
  assets/icon.ico   (Windows, multi-size)
  assets/icon.icns  (macOS, via iconutil -- macOS only)
"""
import os
import shutil
import subprocess
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'assets')
LOGO = os.path.join(OUT, 'logo.png')
SIZE = 1024
PAD_FRACTION = 0.92  # logo fills this fraction of the square canvas


def make_png(png_path):
    logo = Image.open(LOGO).convert('RGBA')
    content = int(SIZE * PAD_FRACTION)
    logo.thumbnail((content, content), Image.LANCZOS)
    canvas = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    canvas.paste(logo, ((SIZE - logo.width) // 2, (SIZE - logo.height) // 2), logo)
    canvas.save(png_path)


def make_ico(png_path, ico_path):
    img = Image.open(png_path)
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, sizes=sizes)


def make_icns(png_path, icns_path):
    if shutil.which('iconutil') is None:
        print('  iconutil not found (macOS only) -- skipping .icns')
        return
    iconset = icns_path + '.iconset'
    if os.path.isdir(iconset):
        shutil.rmtree(iconset)
    os.makedirs(iconset)
    img = Image.open(png_path)
    for s in (16, 32, 128, 256, 512):
        img.resize((s, s), Image.LANCZOS).save(os.path.join(iconset, f'icon_{s}x{s}.png'))
        img.resize((s * 2, s * 2), Image.LANCZOS).save(os.path.join(iconset, f'icon_{s}x{s}@2x.png'))
    subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', icns_path], check=True)
    shutil.rmtree(iconset)


def main():
    if not os.path.isfile(LOGO):
        sys.exit('missing %s' % LOGO)
    os.makedirs(OUT, exist_ok=True)
    png_path = os.path.join(OUT, 'icon.png')
    ico_path = os.path.join(OUT, 'icon.ico')
    icns_path = os.path.join(OUT, 'icon.icns')

    print('reading', LOGO)
    make_png(png_path)
    print('  wrote', png_path)

    make_ico(png_path, ico_path)
    print('  wrote', ico_path)

    make_icns(png_path, icns_path)
    if os.path.exists(icns_path):
        print('  wrote', icns_path)


if __name__ == '__main__':
    sys.exit(main())
