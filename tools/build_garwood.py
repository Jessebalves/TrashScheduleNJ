#!/usr/bin/env python3
"""Build data/garwood.csv: every Borough of Garwood address range and its collection side.

Garwood's DPW picks up garbage in two halves of the borough, split by the railroad (NJ
Transit's Raritan Valley Line, "Conrail RR" in the Census):
    North Side   garbage Tuesday & Friday
    South Side   garbage Monday & Thursday
"North Side includes all of Willow Avenue, New Street, and the dead ends of Myrtle Avenue
off of New Street" (2026 Schedule of Services), although those streets are south of the
railroad. The dead ends of Myrtle Ave off New St are its numbers below 164 (Census: the two
short pieces either side of New St); the rest of Myrtle Ave is South Side.

The addresses are the county street list's Garwood rows
(data/reference/union_county_street_list_2025.csv). Each house range is put on its Census
block side, 15 meters back from its street, and compared with the railroad line.
The county list's election districts are a second opinion: districts 1 and 2 are south of
the railroad, 3 and 4 north of it. Where the two disagree the district is used: Recycle Coach
sided with the district all five times it was asked (Center St, South Ave, Maple St, Oak St;
the Census has some Oak St and Maple St numbers on the wrong side).

Oak St and Maple St have some numbers on both sides of the railroad in the Census; a row
found on both sides keeps the side its election district is on.

Marked to check (Needs_Check), unless a Recycle Coach answer (RECYCLE_COACH) is in the row:
  - Myrtle Ave 164-199 (the dead end off Oak St, not off New St),
  - house numbers the Census does not have (nearest Census number on the same street),
  - streets the Census does not have (the side of their election district).
NOT_IN_TOWN rows are left out (Recycle Coach does not find them in Garwood). The build stops
if any RECYCLE_COACH answer no longer matches.

This is a developer tool, it is not used by the running website. It needs `pyshp` and the
Census ADDRFEAT (address ranges) and EDGES (for the railroad) files for Union County:

    python3 tools/build_garwood.py <folder>/tl_2025_34039_addrfeat <folder>/tl_2025_34039_edges

https://www2.census.gov/geo/tiger/TIGER2025/ADDRFEAT/tl_2025_34039_addrfeat.zip
https://www2.census.gov/geo/tiger/TIGER2025/EDGES/tl_2025_34039_edges.zip
"""
import collections
import csv
import math
import os
import sys

import shapefile  # pip install pyshp

TOP = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, TOP)

from address_lookup import normalize_street  # noqa: E402

COUNTY_FILE = os.path.join(TOP, 'data', 'reference', 'union_county_street_list_2025.csv')
OUT_FILE = os.path.join(TOP, 'data', 'garwood.csv')
ZIP_CODE = '07027'

#Census names -> the county list's name for the same street
CENSUS_NAMES = {'N OAK ST': 'OAK ST', 'S AVE W': 'SOUTH AVE'}
#Always North Side, south of the railroad: (street, lowest, highest number)
NORTH_EXCEPTIONS = [('WILLOW AVE', 0, 99999), ('NEW ST', 0, 99999), ('MYRTLE AVE', 0, 163)]
#Myrtle Ave's dead end off Oak St: South Side, but next to the North Side dead ends
CHECK = [('MYRTLE AVE', 164, 199)]
NORTH_DISTRICTS, SOUTH_DISTRICTS = {'3', '4'}, {'1', '2'}
#On the county list, but not found in Garwood's Recycle Coach
NOT_IN_TOWN = [('MOUNTAIN AVE', 79, 79)]

#Checked in Garwood's Recycle Coach on 2026-11-21 (garbage Tue/Fri = N, Mon/Thu = S)
RECYCLE_COACH = [
    ('NORTH AVE', 306, 'N'), ('3RD AVE', 217, 'N'), ('SPRUCE AVE', 225, 'S'), ('HICKORY AVE', 300, 'S'),
    ('WILLOW AVE', 245, 'N'), ('NEW ST', 210, 'N'), ('MYRTLE AVE', 115, 'N'), ('MYRTLE AVE', 167, 'S'),
    ('MYRTLE AVE', 201, 'S'), ('CENTER ST', 91, 'N'), ('SOUTH AVE', 432, 'N'), ('MAPLE ST', 213, 'N'),
    ('MAPLE ST', 214, 'N'), ('OAK ST', 117, 'N'), ('OAK ST', 416, 'N'), ('OAK ST', 419, 'N'),
    ('BROOKSIDE PL', 405, 'N'), ('CEDAR ST', 5, 'N'),
]

SETBACK = 15
#Garwood's box, for the railroad
BOX = (-74.345, -74.300, 40.640, 40.662)

LAT0, LON0 = 40.65, -74.32
KX, KY = 111320 * math.cos(math.radians(LAT0)), 110950


def to_meters(lon, lat):
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


def read_census(path):
    sides = collections.defaultdict(list)
    for item in shapefile.Reader(path).iterShapeRecords():
        record = item.record.as_dict()
        if ZIP_CODE not in (record['ZIPL'], record['ZIPR']):
            continue
        points = [to_meters(x, y) for x, y in item.shape.points]
        name = normalize_street(record['FULLNAME'] or '')
        name = CENSUS_NAMES.get(name, name)
        for side in 'LR':
            low, high = record[side + 'FROMHN'], record[side + 'TOHN']
            if record['ZIP' + side] != ZIP_CODE or not (low.isdigit() and high.isdigit()):
                continue
            low, high = sorted((int(low), int(high)))
            sides[name].append((low, high, 'E' if low % 2 == 0 else 'O', points, side == 'L'))
    return sides


def read_railroad(path):
    """The railroad's pieces, each drawn west to east, in meters."""
    pieces = []
    for item in shapefile.Reader(path).iterShapeRecords():
        record = item.record.as_dict()
        points = item.shape.points
        if record['MTFCC'] != 'R1011' or not any(BOX[0] < x < BOX[1] and BOX[2] < y < BOX[3] for x, y in points):
            continue
        line = [to_meters(x, y) for x, y in points]
        pieces.append(line if line[0][0] <= line[-1][0] else line[::-1])
    if not pieces:
        sys.exit('No railroad found near Garwood in the EDGES file')
    return pieces


def north_of(railroad, p):
    """Is p north of the railroad (left of it, going east)? And how far from it, in meters."""
    best, best_d = None, math.inf
    for line in railroad:
        for a, b in zip(line, line[1:]):
            l2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
            t = 0 if l2 == 0 else max(0, min(1, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / l2))
            d = math.dist(p, (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            if d < best_d:
                best, best_d = (a, b), d
    a, b = best
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) > 0, best_d


def read_county():
    rows = []
    with open(COUNTY_FILE, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            if row['Municipality'] == 'GARWOOD':
                rows.append((normalize_street(row['Street_Name']), int(row['Low_Range']), int(row['High_Range']),
                             row['Side'], row['District']))
    return rows


def along(points, fraction, left, setback):
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    goal = sum(lengths) * fraction
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if goal <= length and length > 0:
            t = goal / length
            dx, dy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
            sign = 1 if left else -1
            return (a[0] + (b[0] - a[0]) * t - sign * dy * setback, a[1] + (b[1] - a[1]) * t + sign * dx * setback)
        goal -= length
    return points[-1]


def listed(rules, name, low, high):
    return any(name == street and r_low <= low and high <= r_high for street, r_low, r_high in rules)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sides = read_census(sys.argv[1])
    railroad = read_railroad(sys.argv[2])

    out, notes = [], []
    for name, low, high, side, district in read_county():
        if listed(NOT_IN_TOWN, name, low, high):
            notes.append(f'out    {name} {low}-{high}: not in Garwood (Recycle Coach)')
            continue
        by_district = 'N' if district in NORTH_DISTRICTS else 'S'
        if listed(NORTH_EXCEPTIONS, name, low, high):
            out.append((name, low, high, side, 'N', listed(CHECK, name, low, high)))
            continue
        found = [s for s in sides.get(name, []) if s[0] <= high and low <= s[1] and side in (s[2], 'B')]
        check_all = False
        if not found and sides.get(name):
            nearest = min(sides[name], key=lambda s: (min(abs(low - s[0]), abs(low - s[1])), s[2] != side))
            found, check_all = [nearest], True
            notes.append(f'near   {name} {low}-{high}: nearest Census numbers {nearest[0]}-{nearest[1]}')
        if not found:
            out.append((name, low, high, side, by_district, True))
            notes.append(f'guess  {name} {low}-{high}: {by_district}, from election district {district}')
            continue
        placed = []
        for c_low, c_high, parity, points, left in found:
            s_low, s_high = (max(low, c_low), min(high, c_high)) if not check_all else (low, high)
            middle = (s_low + s_high) / 2
            fraction = 0.5 if c_high == c_low else max(0.0, min(1.0, (middle - c_low) / (c_high - c_low)))
            north, distance = north_of(railroad, along(points, fraction, left, SETBACK))
            placed.append((s_low, s_high, parity, 'N' if north else 'S', distance))
        #Oak St and Maple St have the same numbers on both sides of the railroad in the Census:
        #a row found on both sides keeps the one its election district is on
        for s_low, s_high, parity in {p[:3] for p in placed}:
            here = [p for p in placed if p[:3] == (s_low, s_high, parity)]
            if len({p[3] for p in here}) > 1:
                notes.append(f'twice  {name} {s_low}-{s_high}: on both sides in the Census, district {district} '
                             f'({by_district}) kept')
                placed = [p for p in placed if p[:3] != (s_low, s_high, parity) or p[3] == by_district]
        for s_low, s_high, parity, zone, distance in placed:
            check = check_all or listed(CHECK, name, s_low, s_high)
            if zone != by_district:
                notes.append(f'differ {name} {s_low}-{s_high}: {zone} by the railroad ({distance:.0f} m), '
                             f'election district {district} ({by_district}) used')
                zone = by_district
            row_side = side if side != 'B' else ('B' if check_all else parity)
            out.append((name, s_low, s_high, row_side, zone, check))

    #A row with a Recycle Coach answer in it is checked
    answered = lambda r: any(r[0] == n and r[1] <= num <= r[2] and r[3] in ('B', 'E' if num % 2 == 0 else 'O')
                             for n, num, _ in RECYCLE_COACH)
    rows = sorted({(n, lo, hi, sd, z, ch and not answered((n, lo, hi, sd))) for n, lo, hi, sd, z, ch in out})
    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['Municipality', 'Street_Name', 'Low_Range', 'High_Range', 'Side', 'ZIP', 'Zone', 'Needs_Check'])
        for name, low, high, side, zone, check in rows:
            writer.writerow(['GARWOOD', name, low, high, side, ZIP_CODE, zone, 'Y' if check else ''])
    print('\n'.join(notes))
    counts = collections.Counter(r[4] for r in rows)
    print(f'{len(rows)} rows written to {os.path.normpath(OUT_FILE)}, {sum(1 for r in rows if r[5])} to check; '
          f'by side: {dict(sorted(counts.items()))}')
    misses = []
    for name, number, answer in RECYCLE_COACH:
        parity = 'E' if number % 2 == 0 else 'O'
        got = {r[4] for r in rows if r[0] == name and r[1] <= number <= r[2] and r[3] in (parity, 'B')}
        if got != {answer}:
            misses.append(f'{number} {name}: Recycle Coach {answer}, data {sorted(got) or "none"}')
    print(f'Recycle Coach: {len(RECYCLE_COACH) - len(misses)} of {len(RECYCLE_COACH)} agree')
    if misses:
        sys.exit('\n'.join(misses))


if __name__ == '__main__':
    main()
