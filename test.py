#!/usr/bin/env python3

import blendparse

import sys

try:
    blendfile = sys.argv[1]
except IndexError:
    print("Usage: ./test.py <path to .blend>")
    sys.exit()

with blendparse.Blendfile(blendfile) as blend:
    results = [block() for block in blend.get_blocks("SC").values()]
    for structure in results[0]:
        print(structure)
        print(structure.load())