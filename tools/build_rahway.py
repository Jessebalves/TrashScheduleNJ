#!/usr/bin/env python3
"""Build data/rahway.csv: every City of Rahway address range and its collection section.

Rahway's DPW collects in two sections: Section A garbage Monday & Thursday, Section B
Tuesday & Friday; both recycle every other Wednesday (on alternate weeks). The 2026 mailer
(https://www.rahwaynj.gov/DocumentCenter/View/3454/COR_DPW_2026_RecycleSchedule_V2-DIGITAL)
shows the sections on a map, page 2, drawn as vector paths: Section A outlined in purple,
Section B in green, the streets in gray. The two outlines are separated by the Rahway River,
with St Georges Ave, Milton Ave and Main St labeled along it. The map is turned on the page.

This tool:
  1. reads the two outlines and the gray street lines from the PDF (pdftocairo -svg),
  2. lines the map up with the US Census streets: first with the street names printed on
     the map (LABELS: each must sit on its Census street), then with the gray street lines
     (iterated nearest points). About 8 m (median) in the end,
  3. puts each house of the county street list (the Board of Elections' list) on its Census
     block side, 15 meters back from the street, and gives it the section whose outline it is in.

Marked to check (Needs_Check):
  - houses outside both outlines (the river gap, the city edge): the nearer outline, and
    checked when the other one is less than 40 meters further,
  - houses inside an outline but within 20 meters of the other one,
  - house numbers the Census does not have (nearest Census number on the same street),
  - streets the Census does not have (the section most other houses in the same ward and
    election district are in).

The gap between the outlines is drawn wider than the street it stands for, so the houses on
the dividing streets get their section from SIDE_RULES (Recycle Coach answers, 2026-11-21):
St Georges Ave and Milton Ave split by side (west and south A, east and north B), and Main St
up to the 1100 block is A on both sides (the B outline follows the river behind its east side),
except 1047 Main St; from the 1200 block (1245) it is B. Westfield Ave is drawn inside A, but the Census has almost none of
Rahway's numbers on it. The build ends by checking
every address in RECYCLE_COACH.

This is a developer tool, it is not used by the running website. It needs `pyshp`, poppler's
`pdftocairo`, the 2026 mailer PDF and the Census file named in tools/build_kenilworth.py:

    python3 tools/build_rahway.py <2026 mailer PDF> <addrfeat folder>/tl_2025_34039_addrfeat
"""
import collections
import csv
import math
import os
import random
import re
import subprocess
import sys
import tempfile

import shapefile  # pip install pyshp

TOP = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, TOP)

from address_lookup import normalize_street  # noqa: E402

COUNTY_FILE = os.path.join(TOP, 'data', 'reference', 'union_county_street_list_2025.csv')
OUT_FILE = os.path.join(TOP, 'data', 'rahway.csv')
ZIP_CODE = '07065'

#pdftocairo's stroke colors (rgb percentages, first digits) of the two outlines and the streets
SECTION_COLORS = {'43.24': 'A', '16.86': 'B'}
STREET_COLORS = ('82.74', '74.11')

#Street names printed on the map (Census name, page point x, y), read off page 2
LABELS = [
    ('Jaques Ave', 295, 345), ('Bryant St', 295, 325), ('New Brunswick Ave', 310, 378), ('Elizabeth Ave', 543, 343),
    ('E Scott Ave', 545, 397), ('W Scott Ave', 539, 290), ('Saint Georges Ave', 548, 214), ('US Hwy 1', 517, 464),
    ('Irving St', 461, 338), ('E Hazelwood Ave', 462, 515), ('Leesville Ave', 364, 445), ('W Lake Ave', 268, 245),
    ('Grove St', 218, 236), ('W Inman Ave', 195, 236), ('Milton Blvd', 289, 194), ('Madison Ave', 338, 212),
    ('Jefferson Ave', 348, 237), ('W Grand Ave', 478, 268), ('Central Ave', 414, 285), ('Elm Ave', 398, 303),
    ('Lawrence St', 469, 422), ('Washington St', 500, 426), ('E Milton Ave', 485, 447), ('E Grand Ave', 511, 397),
    ('Randolph Ave', 423, 526), ('E Hazelwood Ave', 403, 457), ('Maple Ave', 349, 324), ('Maple Ave', 316, 254),
    ('W Hazelwood Ave', 338, 322), ('Saint Georges Ave', 255, 322), ('Jefferson Ave', 240, 305),
    ('Madison Ave', 226, 284), ('W Inman Ave', 266, 355), ('Whittier St', 515, 294), ('Linden Ave', 561, 279),
    ('Bryant St', 416, 315), ('Main St', 458, 378),
]

#(street, low, high, side O/E/B, section, check): these numbers get this section
SIDE_RULES = [
    ('SAINT GEORGES AVE', 1001, 1599, 'O', 'B', False),  #east side: 1219, 1319 and 1459 are B
    ('SAINT GEORGES AVE', 1200, 1630, 'E', 'A', False),  #west side: 1286 and 1500 are A
    ('SAINT GEORGES AVE', 968, 1198, 'E', 'A', True),    #west side, not in Recycle Coach (1124)
    ('MAIN ST', 1047, 1047, 'O', 'B', False),            #B in Recycle Coach although its neighbors are A
    ('MAIN ST', 700, 999, 'B', 'A', False),              #855 and 868 are A, the river is behind the east side
    ('MAIN ST', 1000, 1099, 'B', 'A', False),            #1001 and 1030 are A; east side A by Street View (user)
    ('MAIN ST', 1100, 1199, 'B', 'A', False),            #1131 is A
    ('MAIN ST', 1201, 1399, 'O', 'B', False),            #1245 is B
    ('MAIN ST', 1200, 1398, 'E', 'B', True),             #not in Recycle Coach (1222)
    ('W MILTON AVE', 1, 299, 'E', 'A', False),           #south side: 64 and 272 are A
    ('W MILTON AVE', 1, 299, 'O', 'B', False),           #north side: 99 and 275 are B
    ('E MILTON AVE', 1, 99, 'O', 'A', False),            #south side, west of Main St: 65 is A
    ('E MILTON AVE', 1, 99, 'E', 'B', False),            #north side: 80 is B
    ('WESTFIELD AVE', 0, 99999, 'B', 'A', False),        #853 and 1001 are A
]

#Checked in Rahway's Recycle Coach on 2026-11-21 (garbage Mon/Thu = A, Tue/Fri = B)
RECYCLE_COACH = [
    ('W INMAN AVE', 578, 'A'), ('JAQUES AVE', 830, 'A'), ('E SCOTT AVE', 533, 'B'), ('LAWRENCE ST', 1652, 'B'),
    ('CENTRAL AVE', 753, 'A'), ('CENTRAL AVE', 405, 'B'), ('BRYANT ST', 552, 'A'), ('BRYANT ST', 1265, 'B'),
    ('W MILTON AVE', 272, 'A'), ('W MILTON AVE', 275, 'B'), ('MAIN ST', 868, 'A'), ('MAIN ST', 855, 'A'),
    ('SAINT GEORGES AVE', 1319, 'B'), ('SAINT GEORGES AVE', 1459, 'B'), ('E HAZELWOOD AVE', 212, 'A'),
    ('E HAZELWOOD AVE', 797, 'B'), ('E ALBERT ST', 263, 'A'), ('E STEARNS ST', 157, 'A'), ('E LAKE AVE', 150, 'A'),
    ('WESTFIELD AVE', 1001, 'A'), ('WESTFIELD AVE', 853, 'A'), ('BROADWAY', 1202, 'A'), ('BARNHARDT LN', 1443, 'B'),
    ('ROSS ST', 971, 'B'),
    #Second round
    ('MAIN ST', 1131, 'A'), ('MAIN ST', 1030, 'A'), ('MAIN ST', 1047, 'B'), ('SAINT GEORGES AVE', 1286, 'A'),
    ('SAINT GEORGES AVE', 1500, 'A'), ('SAINT GEORGES AVE', 1219, 'B'), ('W MILTON AVE', 64, 'A'),
    ('W MILTON AVE', 99, 'B'),
    #Third round (1037 Main St is not in Recycle Coach)
    ('MAIN ST', 1001, 'A'), ('MAIN ST', 1245, 'B'), ('E MILTON AVE', 65, 'A'), ('E MILTON AVE', 80, 'B'),
]

SETBACK = 15
NEAR_OTHER = 20   #inside one outline but this close to the other: check
GAP_MARGIN = 40   #outside both: check unless the other outline is this much further

LAT0, LON0 = 40.60, -74.28
KX, KY = 111320 * math.cos(math.radians(LAT0)), 110950


def to_meters(lon, lat):
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


#----- The map -----

def bezier(p0, p1, p2, p3, steps=8):
    return [tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t ** 2 * c + t ** 3 * d
                  for a, b, c, d in zip(p0, p1, p2, p3)) for t in [i / steps for i in range(1, steps + 1)]]


def path_points(attrs):
    """The lines of one SVG path (curves as short straight pieces), in page points."""
    d = re.search(r' d="([^"]*)"', attrs).group(1)
    matrix = re.search(r'transform="matrix\(([^)]*)\)"', attrs)
    a, b, c, dd, e, f = [float(v) for v in matrix.group(1).split(',')] if matrix else (1, 0, 0, 1, 0, 0)
    tokens = re.findall(r'[MLCZ]|-?[\d.]+', d)
    lines, points, current, n = [], [], None, 0
    while n < len(tokens):
        token = tokens[n]
        if token == 'M':
            if points:
                lines.append(points)
            current = (float(tokens[n + 1]), float(tokens[n + 2]))
            points = [current]
            n += 3
        elif token == 'L':
            current = (float(tokens[n + 1]), float(tokens[n + 2]))
            points.append(current)
            n += 3
        elif token == 'C':
            p1 = (float(tokens[n + 1]), float(tokens[n + 2]))
            p2 = (float(tokens[n + 3]), float(tokens[n + 4]))
            p3 = (float(tokens[n + 5]), float(tokens[n + 6]))
            points += bezier(current, p1, p2, p3)
            current = p3
            n += 7
        else:
            n += 1
    if points:
        lines.append(points)
    return [[(a * x + c * y + e, b * x + dd * y + f) for x, y in line] for line in lines]


def read_map(pdf):
    """({'A': [ring], 'B': [ring]}, [street point]) in page points."""
    with tempfile.TemporaryDirectory() as folder:
        svg_path = os.path.join(folder, 'map.svg')
        subprocess.run(['pdftocairo', '-svg', '-f', '2', '-l', '2', pdf, svg_path], check=True)
        with open(svg_path, encoding='utf-8') as handle:
            svg = handle.read()
    sections, streets = {}, []
    for attrs in re.findall(r'<path([^>]*)/?>', svg):
        color = re.search(r'stroke="rgb\(([^)]*)\)"', attrs)
        if not color or ' d="' not in attrs:
            continue
        color = color.group(1)
        for prefix, section in SECTION_COLORS.items():
            if color.startswith(prefix):
                #The outline is the longest line of the path
                sections[section] = [max(path_points(attrs), key=len)]
        if color.startswith(STREET_COLORS):
            for line in path_points(attrs):
                for p, q in zip(line, line[1:]):
                    n = max(1, int(math.dist(p, q) / 3))
                    streets += [(p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n) for k in range(n)]
    if sorted(sections) != ['A', 'B']:
        sys.exit('Did not find both section outlines on the map: %s' % sorted(sections))
    return sections, streets


#----- Lining the map up -----

class Grid:
    def __init__(self, points, cell=50):
        self.cell = cell
        self.cells = collections.defaultdict(list)
        for p in points:
            self.cells[(int(p[0] // cell), int(p[1] // cell))].append(p)

    def nearest(self, p, radius):
        best, best_d = None, radius
        reach = int(radius // self.cell) + 1
        cx, cy = int(p[0] // self.cell), int(p[1] // self.cell)
        for i in range(cx - reach, cx + reach + 1):
            for j in range(cy - reach, cy + reach + 1):
                for q in self.cells.get((i, j), ()):
                    d = math.dist(p, q)
                    if d < best_d:
                        best, best_d = q, d
        return best, best_d


def solve3(rows, rhs):
    m = [[sum(r[i] * r[j] for r in rows) for j in range(3)] for i in range(3)]
    v = [sum(r[i] * y for r, y in zip(rows, rhs)) for i in range(3)]
    for i in range(3):
        pivot = max(range(i, 3), key=lambda r: abs(m[r][i]))
        m[i], m[pivot], v[i], v[pivot] = m[pivot], m[i], v[pivot], v[i]
        for r in range(3):
            if r != i:
                factor = m[r][i] / m[i][i]
                m[r] = [x - factor * y for x, y in zip(m[r], m[i])]
                v[r] -= factor * v[i]
    return [v[i] / m[i][i] for i in range(3)]


def fit(pairs):
    rows = [(p[0], p[1], 1) for p, _ in pairs]
    return solve3(rows, [q[0] for _, q in pairs]) + solve3(rows, [q[1] for _, q in pairs])


def apply(t, p):
    return (t[0] * p[0] + t[1] * p[1] + t[2], t[3] * p[0] + t[4] * p[1] + t[5])


def nearest_on_lines(p, lines):
    best, best_d = None, math.inf
    for line in lines:
        for a, b in zip(line, line[1:]):
            l2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
            t = 0 if l2 == 0 else max(0, min(1, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / l2))
            q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            if math.dist(p, q) < best_d:
                best, best_d = q, math.dist(p, q)
    return best, best_d


def line_up(street_points, streets_by_name, census_grid):
    """Affine page -> meters: the labels on their streets, then the gray streets on the Census."""
    centers = {name: (sum(p[0] for line in lines for p in line) / sum(len(line) for line in lines),
                      sum(p[1] for line in lines for p in line) / sum(len(line) for line in lines))
               for name, lines in streets_by_name.items()}
    labels = [(name, (x, y)) for name, x, y in LABELS if name in streets_by_name]
    t = fit([(p, centers[name]) for name, p in labels])
    for _ in range(30):
        found = [(p, *nearest_on_lines(apply(t, p), streets_by_name[name])) for name, p in labels]
        limit = sorted(d for _, _, d in found)[int(len(found) * 0.85)]
        t = fit([(p, q) for p, q, d in found if d <= limit])
    random.seed(1)
    sample = random.sample(street_points, min(4000, len(street_points)))
    for step in range(20):
        radius = 60 if step < 6 else (35 if step < 12 else 20)
        found = [(p, *census_grid.nearest(apply(t, p), radius)) for p in sample]
        found = sorted([f for f in found if f[1] is not None], key=lambda f: f[2])
        t = fit([(p, q) for p, q, _ in found[:int(len(found) * 0.8)]])
    gaps = [d for _, _, d in found]
    print(f'Map streets are {gaps[len(gaps) // 2]:.1f} m (median) from the Census streets '
          f'({len(found)} of {len(sample)} within 20 m)')
    return t


#----- Census, county list, sections -----

def read_census(path):
    sides = collections.defaultdict(list)
    lines_by_name = collections.defaultdict(list)
    for item in shapefile.Reader(path).iterShapeRecords():
        record = item.record.as_dict()
        if ZIP_CODE not in (record['ZIPL'], record['ZIPR']):
            continue
        points = [to_meters(x, y) for x, y in item.shape.points]
        lines_by_name[record['FULLNAME'] or ''].append(points)
        name = normalize_street(record['FULLNAME'] or '')
        for side in 'LR':
            low, high = record[side + 'FROMHN'], record[side + 'TOHN']
            if record['ZIP' + side] != ZIP_CODE or not (low.isdigit() and high.isdigit()):
                continue
            low, high = sorted((int(low), int(high)))
            sides[name].append((low, high, 'E' if low % 2 == 0 else 'O', points, side == 'L'))
    return sides, lines_by_name


def read_county():
    rows = []
    with open(COUNTY_FILE, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            if row['Municipality'] == 'RAHWAY':
                rows.append((normalize_street(row['Street_Name']), int(row['Low_Range']), int(row['High_Range']),
                             row['Side'], row['Ward'], row['District']))
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


def inside(ring, p):
    result = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1):
            result = not result
    return result


def section_of(outlines, p):
    """(section, check) for a house at p (meters)."""
    distance = {s: nearest_on_lines(p, [ring + ring[:1]])[1] for s, ring in outlines.items()}
    within = [s for s, ring in outlines.items() if inside(ring, p)]
    if len(within) == 1:
        other = 'B' if within[0] == 'A' else 'A'
        return within[0], distance[other] < NEAR_OTHER
    nearer = min(distance, key=distance.get)
    other = 'B' if nearer == 'A' else 'A'
    return nearer, distance[other] - distance[nearer] < GAP_MARGIN


def side_rule(name, low, high, side):
    """(section, check) from SIDE_RULES for a row inside one rule, else None."""
    for street, r_low, r_high, r_side, section, check in SIDE_RULES:
        if name == street and r_low <= low and high <= r_high and r_side in ('B', side):
            return section, check
    return None


def recycle_coach_misses(rows):
    misses = []
    for name, number, answer in RECYCLE_COACH:
        parity = 'E' if number % 2 == 0 else 'O'
        got = {r[4] for r in rows if r[0] == name and r[1] <= number <= r[2] and r[3] in (parity, 'B')}
        if got != {answer}:
            misses.append(f'{number} {name}: Recycle Coach {answer}, data {sorted(got) or "none"}')
    return misses


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sections, street_points = read_map(sys.argv[1])
    sides, lines_by_name = read_census(sys.argv[2])
    census_points = []
    for lines in lines_by_name.values():
        for line in lines:
            for a, b in zip(line, line[1:]):
                n = max(1, int(math.dist(a, b) / 5))
                census_points += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]
    t = line_up(street_points, lines_by_name, Grid(census_points))
    outlines = {s: [apply(t, p) for p in rings[0]] for s, rings in sections.items()}

    out, notes, unplaced = [], [], []
    placed = collections.defaultdict(collections.Counter)
    for name, low, high, side, ward, district in read_county():
        found = [s for s in sides.get(name, []) if s[0] <= high and low <= s[1] and side in (s[2], 'B')]
        check_all = False
        if not found and sides.get(name):
            nearest = min(sides[name], key=lambda s: (min(abs(low - s[0]), abs(low - s[1])), s[2] != side))
            found, check_all = [nearest], True
            notes.append(f'near   {name} {low}-{high}: nearest Census numbers {nearest[0]}-{nearest[1]}')
        if not found:
            unplaced.append((name, low, high, side, ward, district))
            continue
        for c_low, c_high, parity, points, left in found:
            s_low, s_high = (max(low, c_low), min(high, c_high)) if not check_all else (low, high)
            middle = (s_low + s_high) / 2
            fraction = 0.5 if c_high == c_low else max(0.0, min(1.0, (middle - c_low) / (c_high - c_low)))
            section, check = section_of(outlines, along(points, fraction, left, SETBACK))
            row_side = side if side != 'B' else ('B' if check_all else parity)
            ruled = side_rule(name, s_low, s_high, row_side)
            if ruled:
                section, check = ruled
            else:
                check = check or check_all
            out.append((name, s_low, s_high, row_side, section, check))
            placed[(ward, district)][section] += 1

    for name, low, high, side, ward, district in unplaced:
        counts = placed[(ward, district)]
        if not counts:
            notes.append(f'skip   {name} {low}-{high}: not on the Census map, no other street in ward {ward} district {district}')
            continue
        section, check = side_rule(name, low, high, side) or (counts.most_common(1)[0][0], True)
        out.append((name, low, high, side, section, check))
        notes.append(f'guess  {name} {low}-{high}: {section}, from ward {ward} district {district} {dict(counts)}')

    rows = sorted(set(out))
    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['Municipality', 'Street_Name', 'Low_Range', 'High_Range', 'Side', 'ZIP', 'Zone', 'Needs_Check'])
        for name, low, high, side, section, check in rows:
            writer.writerow(['RAHWAY', name, low, high, side, ZIP_CODE, section, 'Y' if check else ''])
    print('\n'.join(notes))
    counts = collections.Counter(r[4] for r in rows)
    print(f'{len(rows)} rows written to {os.path.normpath(OUT_FILE)}, {sum(1 for r in rows if r[5])} to check; '
          f'by section: {dict(sorted(counts.items()))}')
    misses = recycle_coach_misses(rows)
    print(f'Recycle Coach: {len(RECYCLE_COACH) - len(misses)} of {len(RECYCLE_COACH)} agree')
    if misses:
        sys.exit('\n'.join(misses))


if __name__ == '__main__':
    main()
