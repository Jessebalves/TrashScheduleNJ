#!/usr/bin/env python3
"""Build data/springfield.csv: every Township of Springfield address range and its trash side.

Springfield's 2026 DPW Services Brochure: "Collection is on Thursdays for residents on the
south side of Mountain Ave and Fridays for residents on the north side of Mountain Ave"
(Monday & Thursday and Tuesday & Friday in summer). Mountain Ave runs from the Mountainside
line in the southwest to Morris Ave in the northeast, so "north" is the northwest side and
"south" the southeast side. Past its ends the line is carried on straight (EXTEND meters):
that decides the neighborhoods beyond Morris Ave.

The addresses are the county street list's Springfield rows
(data/reference/union_county_street_list_2025.csv), each put on its Census block side 15 m
back from its street and compared with the Mountain Ave line. Houses on Mountain Ave itself
go by their side of the street.

Recycle Coach confirmed 17 addresses (RECYCLE_COACH), nine of them near the line or past its
northeast end (Morris Ave, Linden Ave, Short Hills Ave, Meisel Ave, Caldwell Pl, Millburn Ave,
Church Mall, Center St), so the straight extension is not marked to check. The build stops if
any answer no longer matches.

Marked to check (Needs_Check), unless a Recycle Coach answer is in the row:
  - houses within NEAR meters of the line (cross streets at Mountain Ave),
  - a row whose election district is mostly on the other side,
  - house numbers the Census does not have, streets the Census does not have (district's side).

This is a developer tool, it is not used by the running website. It needs `pyshp` and the
Census ADDRFEAT (Union County) and COUSUB (New Jersey) files:

    python3 tools/build_springfield.py <folder>/tl_2025_34039_addrfeat <folder>/tl_2025_34_cousub
"""
import collections
import csv
import math
import os
import sys

import shapefile  # pip install pyshp

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.join(HERE, '..')
sys.path.insert(0, TOP)
sys.path.insert(0, HERE)

from address_lookup import normalize_street  # noqa: E402
from build_garwood import along, to_meters  # noqa: E402

COUNTY_FILE = os.path.join(TOP, 'data', 'reference', 'union_county_street_list_2025.csv')
OUT_FILE = os.path.join(TOP, 'data', 'springfield.csv')
ZIP_CODE = '07081'
SETBACK = 15
NEAR = 25
EXTEND = 3000
#Checked in Springfield's Recycle Coach on 2026-11-21 (trash Friday = N, Thursday = S)
RECYCLE_COACH = [
    ('BALTUSROL WAY', 132, 'N'), ('MILLTOWN RD', 216, 'S'), ('S SPRINGFIELD AVE', 180, 'S'), ('MOUNTAIN AVE', 330, 'N'),
    ('MOUNTAIN AVE', 345, 'S'), ('HILLSIDE AVE', 270, 'S'), ('HILLSIDE AVE', 307, 'N'), ('MORRIS AVE', 190, 'S'),
    ('MORRIS AVE', 240, 'N'), ('LINDEN AVE', 40, 'S'), ('SHORT HILLS AVE', 236, 'N'), ('MEISEL AVE', 20, 'S'),
    ('CALDWELL PL', 16, 'N'), ('MILLBURN AVE', 92, 'N'), ('CHURCH MALL', 18, 'S'), ('CENTER ST', 20, 'N'),
    ('NEWBROOK LN', 99, 'S'),
]

#County list spellings that are typing slips (or a unit letter in front) -> the street's name
COUNTY_NAMES = {'REMER AVENUE AVE': 'REMER AVE', 'MEISEL AVENUE AVE': 'MEISEL AVE', 'A FOREST DR': 'FOREST DR',
                'B TROY DR': 'TROY DR'}


def township(path):
    for item in shapefile.Reader(path).iterShapeRecords():
        record = item.record.as_dict()
        if record['NAME'] == 'Springfield' and record['COUNTYFP'] == '039':
            return [to_meters(x, y) for x, y in item.shape.points]
    sys.exit('Springfield is not in the COUSUB file')


def inside(ring, p):
    result = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1):
            result = not result
    return result


def read_census(path, ring):
    """Census address ranges inside the township, and Mountain Ave's line (southwest to northeast)."""
    sides = collections.defaultdict(list)
    mountain = []
    for item in shapefile.Reader(path).iterShapeRecords():
        record = item.record.as_dict()
        points = [to_meters(x, y) for x, y in item.shape.points]
        if not inside(ring, points[len(points) // 2]):
            continue
        name = normalize_street(record['FULLNAME'] or '')
        if name == 'MOUNTAIN AVE':
            mountain += points
        for side in 'LR':
            low, high = record[side + 'FROMHN'], record[side + 'TOHN']
            if not (low.isdigit() and high.isdigit()):
                continue
            low, high = sorted((int(low), int(high)))
            sides[name].append((low, high, 'E' if low % 2 == 0 else 'O', points, side == 'L'))
    #Mountain Ave is nearly straight: order its points along its own direction
    (x0, y0), (x1, y1) = min(mountain, key=lambda p: p[0] + p[1]), max(mountain, key=lambda p: p[0] + p[1])
    length = math.dist((x0, y0), (x1, y1))
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    line = sorted(set(mountain), key=lambda p: (p[0] - x0) * ux + (p[1] - y0) * uy)
    start = (line[0][0] - ux * EXTEND, line[0][1] - uy * EXTEND)
    end = (line[-1][0] + ux * EXTEND, line[-1][1] + uy * EXTEND)
    return sides, [start] + line + [end]


def north_of(line, p):
    """Is p on the northwest side of the line (left of it, going northeast)? And how far from it."""
    best, best_d = None, math.inf
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
            if row['Municipality'] == 'SPRINGFIELD':
                name = normalize_street(row['Street_Name'])
                rows.append((COUNTY_NAMES.get(name, name), int(row['Low_Range']), int(row['High_Range']),
                             row['Side'], row['District']))
    return rows


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    ring = township(sys.argv[2])
    sides, line = read_census(sys.argv[1], ring)

    placed, unplaced, notes = [], [], []
    for name, low, high, side, district in read_county():
        found = [s for s in sides.get(name, []) if s[0] <= high and low <= s[1] and side in (s[2], 'B')]
        check_all = False
        if not found and sides.get(name):
            nearest = min(sides[name], key=lambda s: (min(abs(low - s[0]), abs(low - s[1])), s[2] != side))
            found, check_all = [nearest], True
        if not found:
            unplaced.append((name, low, high, side, district))
            continue
        for c_low, c_high, parity, points, left in found:
            s_low, s_high = (max(low, c_low), min(high, c_high)) if not check_all else (low, high)
            middle = (s_low + s_high) / 2
            fraction = 0.5 if c_high == c_low else max(0.0, min(1.0, (middle - c_low) / (c_high - c_low)))
            p = along(points, fraction, left, SETBACK)
            north, distance = north_of(line, p)
            row_side = side if side != 'B' else ('B' if check_all else parity)
            #A house on Mountain Ave itself goes by its side of the street, which is certain
            near = distance < NEAR and name != 'MOUNTAIN AVE'
            placed.append([name, s_low, s_high, row_side, 'N' if north else 'S', district,
                           check_all or near])

    #Election districts: the side most of their houses are on
    by_district = collections.defaultdict(collections.Counter)
    for row in placed:
        by_district[row[5]][row[4]] += 1
    for row in placed:
        counts = by_district[row[5]]
        majority, votes = counts.most_common(1)[0]
        if row[4] != majority and votes >= 0.9 * sum(counts.values()):
            row[6] = True
            notes.append(f'differ {row[0]} {row[1]}-{row[2]}: {row[4]}, district {row[5]} is {dict(counts)}')
    for name, low, high, side, district in unplaced:
        counts = by_district[district]
        zone = counts.most_common(1)[0][0] if counts else 'S'
        placed.append([name, low, high, side, zone, district, True])
        notes.append(f'guess  {name} {low}-{high}: {zone}, from district {district} {dict(counts)}')

    answered = lambda r: any(r[0] == n and r[1] <= num <= r[2] and r[3] in ('B', 'E' if num % 2 == 0 else 'O')
                             for n, num, _ in RECYCLE_COACH)
    rows = sorted({(r[0], r[1], r[2], r[3], r[4], r[6] and not answered(r)) for r in placed})
    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['Municipality', 'Street_Name', 'Low_Range', 'High_Range', 'Side', 'ZIP', 'Zone', 'Needs_Check'])
        for name, low, high, side, zone, check in rows:
            writer.writerow(['SPRINGFIELD', name, low, high, side, ZIP_CODE, zone, 'Y' if check else ''])
    print('\n'.join(notes))
    print('districts:', {d: dict(c) for d, c in sorted(by_district.items())})
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
