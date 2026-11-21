#!/usr/bin/env python3
"""Build data/westfield.csv: every Town of Westfield address range and its recycling zone.

Westfield does not collect household trash (residents hire private haulers). The town's
contractor, Interstate Waste Services, picks up recycling every other week in ten zones:
Zones 1-5 north of the railroad, 6-10 south of it, one weekday each.

The town publishes the zones only as maps:
  - the Engineering Dept's "Recycling Collection Zones" CAD drawing (November 19, 2020):
        https://www.westfieldnj.gov/DocumentCenter/View/1759
    Each zone is hatched with dots of its own color (Zones 5 and 9 share cyan; 5 is north
    of the railroad, 9 south). Gray lines are the streets.
  - the 2026 mailer's map, which names the streets the zone lines run along (BOUNDARY_STREETS).

This tool:
  1. reads the colored dots and the gray street lines from the drawing (pdftocairo -svg),
  2. lines the drawing up with the US Census streets: an affine fit of the gray street
     lines to the Census street lines (iterated nearest points), one fit for the north half
     and one for the south half (the south half fits less well, about 10 m against 6 m),
  3. puts each house of the county street list (the Board of Elections' list) on its
     Census block side, 20 meters back from the street, and gives it the zone of the
     dots around it,
  4. south of the railroad, a house alongside a street the mailer names as a zone line gets
     the zone on its own side of that street. The drawing's south lines sit up to about
     90 m off those streets, so this step is what places the houses along them.

Checked against Recycle Coach on 2026-11-21: 25 addresses, all right (tests/test_westfield.py).

Marked to check (Needs_Check):
  - houses on a zone-line street itself (the town does not say which side counts), unless
    Recycle Coach confirmed that street's sides (SIDES_CONFIRMED),
  - houses where the dots around them are of two zones and no named street decides it
    (the north side's zone lines, the town border),
  - house numbers the Census does not have (nearest Census number on the same street),
  - streets the Census does not have (the zone most other houses in the same ward and
    election district are in).

This is a developer tool, it is not used by the running website. It needs `pyshp`,
poppler's `pdftocairo`, the zone map PDF and the Census file named in tools/build_kenilworth.py:

    python3 tools/build_westfield.py <zone map PDF> <addrfeat folder>/tl_2025_34039_addrfeat
"""
import collections
import csv
import json
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
OUT_FILE = os.path.join(TOP, 'data', 'westfield.csv')
ZIP_CODE = '07090'

#Zone colors in the drawing (pdftocairo's rgb percentages)
ZONE_COLORS = {
    '100%, 0%, 0%': '1', '100%, 0%, 100%': '2', '0%, 0%, 100%': '3', '0%, 100%, 0%': '4',
    '0%, 100%, 100%': '5/9', '100%, 49.798584%, 0%': '6', '72.198486%, 63.09967%, 36.099243%': '7',
    '74.899292%, 0%, 100%': '8', '100%, 74.899292%, 0%': '10',
}
STREET_GRAY = '86.299133%, 86.299133%, 86.299133%'
#Page points: cyan dots left of this are Zone 5, right of it Zone 9
CYAN_SPLIT_X = 750
#Page points: the railroad runs at about y = 1330; each half is fitted with the streets on its side
NORTH_STREETS_MAX_Y = 1360
SOUTH_STREETS_MIN_Y = 1300

#The streets the 2026 mailer's map draws the south side's zone lines along (Census names).
#North of the railroad the drawing lines up with the Census within about 6 m and its own
#lines are used (Prospect St, Madison Ave, Dudley Ave, N Euclid Ave, E Broad St, S Chestnut St
#and Mountain Ave, the unnamed line between Zones 3 and 4, all checked in Recycle Coach); a
#side-of-street rule there put some of Gallows Hill Rd in the wrong zone.
BOUNDARY_STREETS = {
    'RAHWAY AVE', 'SHACKAMAXON DR', 'GROVE ST', 'E GROVE ST', 'MONTAUK DR', 'SUMMIT AVE',
    'CLOVER ST', 'ROGER AVE',
}

#County list spellings -> the street's name in data/westfield.csv
COUNTY_NAMES = {
    'NORGATE': 'NORGATE RD', 'VILLAGE GRN': 'VILLAGE GREEN', 'WATCHUNG FRK': 'WATCHUNG FORK',
    'DARTMOOR': 'DARTMOOR ST', 'OAK TREE PASS': 'OAKTREE PASS', 'HAWTHORN DR': 'HAWTHORNE DR',
    'A SANDRA CIR': 'SANDRA CIR', 'B SANDRA CIR': 'SANDRA CIR', 'BOYNTON AVEUE': 'BOYNTON AVE',
    'BRANDT': 'BRANDT CT', 'GROVE ST W': 'W GROVE ST',
    #The county list (and the Census) mostly write W Grove St as plain "Grove St"; Google says "W Grove St"
    'GROVE ST': 'W GROVE ST', 'US HIGHWAY 22 E': 'US HWY 22', 'STATE ROUTE 22 E': 'US HWY 22',
}
#Names in data/westfield.csv the Census writes another way
CENSUS_NAMES = {'MOUNTAIN AVE': 'MOUNTAIN AVE E', 'S SCOTCH PLAINS AVE': 'SCOTCH PLAINS AVE', 'W GROVE ST': 'GROVE ST'}

#North of the railroad the zone lines the mailer names (and Mountain Ave, the unnamed line
#between Zones 3 and 4) decide only for the houses on those streets themselves
NORTH_LINE_STREETS = {
    'PROSPECT ST', 'MADISON AVE', 'W DUDLEY AVE', 'E DUDLEY AVE', 'N EUCLID AVE', 'E BROAD ST',
    'SPRINGFIELD AVE', 'S CHESTNUT ST', 'MOUNTAIN AVE E',
}

#Zone-line streets whose two sides Recycle Coach confirmed (2026-11-21): their houses are not marked to check
SIDES_CONFIRMED = {'GROVE ST', 'ROGER AVE', 'RAHWAY AVE', 'SHACKAMAXON DR', 'N EUCLID AVE', 'E BROAD ST', 'MOUNTAIN AVE E'}

SETBACK = 20        #meters from the street line to a house
VOTE_RADIUS = 40    #meters around a house to count zone dots
NEAR_BOUNDARY = 120  #a house this close to a boundary street is placed by its side of that street
PROBE = 150         #meters each side of a boundary street to read the two zones
MIXED = 0.25        #a second zone with this share of the dots around a house: check

LAT0, LON0 = 40.65, -74.35
KX, KY = 111320 * math.cos(math.radians(LAT0)), 110950


def to_meters(lon, lat):
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


#----- The drawing -----

def read_drawing(pdf):
    """({color: [page point]}) for every stroked point in the drawing."""
    with tempfile.TemporaryDirectory() as folder:
        svg_path = os.path.join(folder, 'map.svg')
        subprocess.run(['pdftocairo', '-svg', pdf, svg_path], check=True)
        with open(svg_path, encoding='utf-8') as handle:
            svg = handle.read()
    points = collections.defaultdict(list)
    for attrs in re.findall(r'<path([^>]*)/?>', svg):
        color = re.search(r'stroke="rgb\(([^)]*)\)"', attrs)
        d = re.search(r' d="([^"]*)"', attrs)
        if not color or not d:
            continue
        matrix = re.search(r'transform="matrix\(([^)]*)\)"', attrs)
        a, b, c, dd, e, f = [float(v) for v in matrix.group(1).split(',')] if matrix else (1, 0, 0, 1, 0, 0)
        numbers = re.findall(r'-?[\d.]+', d.group(1))
        for n in range(0, len(numbers) - 1, 2):
            x, y = float(numbers[n]), float(numbers[n + 1])
            points[color.group(1)].append((a * x + c * y + e, b * x + dd * y + f))
    missing = [c for c in list(ZONE_COLORS) + [STREET_GRAY] if c not in points]
    if missing:
        sys.exit('These colors are not in the drawing: %s' % missing)
    return points


class Grid:
    """Points in square cells, for nearest-point and within-radius searches."""

    def __init__(self, items, cell):
        self.cell = cell
        self.cells = collections.defaultdict(list)
        for point, value in items:
            self.cells[(int(point[0] // cell), int(point[1] // cell))].append((point, value))

    def near(self, p, radius):
        reach = int(radius // self.cell) + 1
        cx, cy = int(p[0] // self.cell), int(p[1] // self.cell)
        for i in range(cx - reach, cx + reach + 1):
            for j in range(cy - reach, cy + reach + 1):
                for q, value in self.cells.get((i, j), ()):
                    if (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 <= radius * radius:
                        yield q, value


def solve3(rows, rhs):
    """Least squares for x in rows . x = rhs, three unknowns."""
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


def apply(t, p):
    return (t[0] * p[0] + t[1] * p[1] + t[2], t[3] * p[0] + t[4] * p[1] + t[5])


def fit(gray, street_grid, start, label):
    """Affine page -> meters fit of the drawing's street lines to the Census streets."""
    random.seed(1)
    sample = random.sample(gray, min(4000, len(gray)))
    t = start
    for step in range(25):
        reach = 300 if step < 5 else (150 if step < 12 else 50)
        pairs = []
        for p in sample:
            q = apply(t, p)
            best = min(street_grid.near(q, reach), key=lambda item: math.dist(item[0], q), default=None)
            if best:
                pairs.append((p, best[0], math.dist(best[0], q)))
        pairs.sort(key=lambda pair: pair[2])
        keep = pairs[:int(len(pairs) * 0.8)]
        rows = [(p[0], p[1], 1) for p, _, _ in keep]
        t = solve3(rows, [q[0] for _, q, _ in keep]) + solve3(rows, [q[1] for _, q, _ in keep])
    gaps = sorted(pair[2] for pair in pairs)
    print(f'{label} half: drawing streets are {gaps[len(gaps) // 2]:.1f} m (median) from the Census streets')
    return t


#----- Census and county list -----

def read_census(path):
    """({name: [block side]}, [(street name, line)]); a block side is (low, high, parity, line, is left)."""
    sides = collections.defaultdict(list)
    lines = []
    for item in shapefile.Reader(path).iterShapeRecords():
        record = item.record.as_dict()
        if ZIP_CODE not in (record['ZIPL'], record['ZIPR']):
            continue
        points = [to_meters(x, y) for x, y in item.shape.points]
        name = normalize_street(record['FULLNAME'] or '')
        lines.append((name, points))
        for side in 'LR':
            low, high = record[side + 'FROMHN'], record[side + 'TOHN']
            if record['ZIP' + side] != ZIP_CODE or not (low.isdigit() and high.isdigit()):
                continue
            low, high = sorted((int(low), int(high)))
            sides[name].append((low, high, 'E' if low % 2 == 0 else 'O', points, side == 'L'))
    return sides, lines


def read_county():
    rows = []
    with open(COUNTY_FILE, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            if row['Municipality'] == 'WESTFIELD':
                name = normalize_street(row['Street_Name'])
                rows.append((COUNTY_NAMES.get(name, name), int(row['Low_Range']), int(row['High_Range']),
                             row['Side'], row['Ward'], row['District']))
    return rows


def along(points, fraction, left, setback):
    """The point `fraction` of the way along a line, `setback` meters to one side."""
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


#----- Zones -----

def segment_distance(p, a, b):
    length = math.dist(a, b)
    if length == 0:
        return math.dist(p, a)
    t = max(0, min(1, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / length ** 2))
    return math.dist(p, (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))


class Zones:
    def __init__(self, dots, boundary_lines, north_ave, south_ave):
        self.dots = Grid(dots, 50)
        #North Ave runs along the north side of the railroad and South Ave along the south
        #side: a house nearer North Ave is north of the railroad (Zones 1-5)
        self.north_ave = [(a, b) for line in north_ave for a, b in zip(line, line[1:])]
        self.south_ave = [(a, b) for line in south_ave for a, b in zip(line, line[1:])]
        #Boundary street pieces: (a, b, street name)
        self.pieces = Grid([(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), (a, b, name))
                            for name, line in boundary_lines for a, b in zip(line, line[1:])], 100)

    def north(self, p):
        return (min(segment_distance(p, a, b) for a, b in self.north_ave)
                < min(segment_distance(p, a, b) for a, b in self.south_ave))

    def votes(self, p, radius=VOTE_RADIUS):
        north = self.north(p)
        return collections.Counter(zone for _, zone in self.dots.near(p, radius) if (int(zone) <= 5) == north)

    def zone_at(self, p, radius=VOTE_RADIUS):
        votes = self.votes(p, radius)
        if votes:
            return votes.most_common(1)[0][0]
        north = self.north(p)
        nearest = min((item for item in self.dots.near(p, 250) if (int(item[1]) <= 5) == north),
                      key=lambda item: math.dist(item[0], p), default=None)
        return nearest[1] if nearest else None

    def nearest_boundary(self, p, only=None):
        """(distance, point on the street, unit normal, street name) of the nearest boundary street piece."""
        best = None
        for _, (a, b, name) in self.pieces.near(p, NEAR_BOUNDARY + 150):
            if (only is not None and name != only) or (only is None and name not in BOUNDARY_STREETS):
                continue
            length = math.dist(a, b)
            if length == 0:
                continue
            t = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / length ** 2
            #Only a street the house is alongside: past the end of Clover St (Cambridge Rd) the
            #zone line has already turned onto Roger Ave
            if not 0 <= t <= 1:
                continue
            q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            normal = (-(b[1] - a[1]) / length, (b[0] - a[0]) / length)
            d = math.dist(p, q)
            if best is None or d < best[0]:
                best = (d, q, normal, name)
        return best

    def place(self, p, street):
        """(zone, check) for a house at p on `street`."""
        votes = self.votes(p)
        zone = self.zone_at(p)
        near = self.nearest_boundary(p, street if street in NORTH_LINE_STREETS else None)
        if near and near[0] <= NEAR_BOUNDARY:
            _, q, n, name = near
            left = self.zone_at((q[0] + n[0] * PROBE, q[1] + n[1] * PROBE), 60)
            right = self.zone_at((q[0] - n[0] * PROBE, q[1] - n[1] * PROBE), 60)
            north = self.north(p)
            #Both sides must be on the house's side of the railroad (Rahway Ave starts at South Ave)
            if left and right and left != right and (int(left) <= 5) == north == (int(right) <= 5):
                on_left = (p[0] - q[0]) * n[0] + (p[1] - q[1]) * n[1] > 0
                return (left if on_left else right), street == name and name not in SIDES_CONFIRMED
        if votes and len(votes) > 1:
            second = votes.most_common(2)[1][1]
            if second >= MIXED * sum(votes.values()):
                return zone, True
        return zone, False


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    drawing = read_drawing(sys.argv[1])
    sides, lines = read_census(sys.argv[2])

    street_grid = Grid([(p, None) for _, line in lines for a, b in zip(line, line[1:])
                        for p in [(a[0] + (b[0] - a[0]) * i / max(1, int(math.dist(a, b) / 5)),
                                   a[1] + (b[1] - a[1]) * i / max(1, int(math.dist(a, b) / 5)))
                                  for i in range(max(1, int(math.dist(a, b) / 5)) + 1)]], 50)
    zone_points = [p for color in ZONE_COLORS for p in drawing[color]]
    census_points = [p for _, line in lines for p in line]

    def box(points):
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        return min(xs), max(xs), min(ys), max(ys)
    mx0, mx1, my0, my1 = box(zone_points)
    cx0, cx1, cy0, cy1 = box(census_points)
    sx, sy = (cx1 - cx0) / (mx1 - mx0), -(cy1 - cy0) / (my1 - my0)
    start = [sx, 0, cx0 - sx * mx0, 0, sy, cy1 - sy * my0]
    gray = drawing[STREET_GRAY]
    whole = fit(gray, street_grid, start, 'Whole')
    north = fit([p for p in gray if p[1] < NORTH_STREETS_MAX_Y], street_grid, whole, 'North')
    south = fit([p for p in gray if p[1] > SOUTH_STREETS_MIN_Y], street_grid, whole, 'South')

    dots = []
    for color, zone in ZONE_COLORS.items():
        for p in drawing[color]:
            z = zone if zone != '5/9' else ('5' if p[0] < CYAN_SPLIT_X else '9')
            dots.append((apply(north if int(z) <= 5 else south, p), z))
    zones = Zones(dots, [(name, line) for name, line in lines if name in BOUNDARY_STREETS | NORTH_LINE_STREETS],
                  [line for name, line in lines if name in ('N AVE W', 'N AVE E')],
                  [line for name, line in lines if name in ('S AVE W', 'S AVE E')])

    out, notes, unplaced = [], [], []
    placed = collections.defaultdict(collections.Counter)
    for name, low, high, side, ward, district in read_county():
        census_name = CENSUS_NAMES.get(name, name)
        found = [s for s in sides.get(census_name, []) if s[0] <= high and low <= s[1] and side in (s[2], 'B')]
        check_all = False
        if not found and sides.get(census_name):
            #A house number the Census does not have: the nearest one on the same street
            nearest = min(sides[census_name], key=lambda s: (min(abs(low - s[0]), abs(low - s[1])), s[2] != side))
            found, check_all = [nearest], True
            notes.append(f'near   {name} {low}-{high}: nearest Census numbers {nearest[0]}-{nearest[1]}')
        if not found:
            unplaced.append((name, low, high, side, ward, district))
            continue
        for c_low, c_high, parity, points, left in found:
            s_low, s_high = (max(low, c_low), min(high, c_high)) if not check_all else (low, high)
            middle = (s_low + s_high) / 2
            fraction = 0.5 if c_high == c_low else max(0.0, min(1.0, (middle - c_low) / (c_high - c_low)))
            zone, check = zones.place(along(points, fraction, left, SETBACK), census_name)
            if zone is None:
                notes.append(f'none   {name} {s_low}-{s_high}: no zone near it on the map')
                continue
            row_side = side if side != 'B' else ('B' if check_all else parity)
            out.append((name, s_low, s_high, row_side, zone, check or check_all))
            placed[(ward, district)][zone] += 1

    for name, low, high, side, ward, district in unplaced:
        counts = placed[(ward, district)]
        if not counts:
            notes.append(f'skip   {name} {low}-{high}: not on the Census map, no other street in ward {ward} district {district}')
            continue
        zone = counts.most_common(1)[0][0]
        out.append((name, low, high, side, zone, True))
        notes.append(f'guess  {name} {low}-{high}: {zone}, from ward {ward} district {district} {dict(counts)}')

    #One row per stretch: a range split over two block sides with the same answer is joined back
    rows = sorted(set(out))
    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['Municipality', 'Street_Name', 'Low_Range', 'High_Range', 'Side', 'ZIP', 'Zone', 'Needs_Check'])
        for name, low, high, side, zone, check in rows:
            writer.writerow(['WESTFIELD', name, low, high, side, ZIP_CODE, zone, 'Y' if check else ''])
    print('\n'.join(notes))
    counts = collections.Counter(r[4] for r in rows)
    print(f'{len(rows)} rows written to {os.path.normpath(OUT_FILE)}, {sum(1 for r in rows if r[5])} to check; '
          f'by zone: {dict(sorted(counts.items(), key=lambda kv: int(kv[0])))}')


if __name__ == '__main__':
    main()
