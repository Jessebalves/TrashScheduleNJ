#!/usr/bin/env python3
"""Build data/linden.csv: every City of Linden address range and its DPW collection district.

Linden collects by ten DPW collection districts. They are NOT the city's wards: the
DPW drew them on its own map (July 2020), and the wards were redrawn in 2022. Whole
neighborhoods differ (Baldwin Ave is ward 1 but district 3, Debra Dr ward 10 but
district 1), so the county list's ward cannot be used.

The map, "DPW Residential Solid Waste COLLECTION DISTRICTS", is a CAD drawing:
    https://linden-nj.gov/wp-content/uploads/2021/01/DPW-Collection-District.pdf
Each district is filled with its own color, and those fills are in the PDF as triangles.
This tool:
  1. reads the triangles of each district color (pdftocairo -svg),
  2. lines the drawing up with the US Census street map: the street names printed on the
     map (pdftotext -bbox) must sit on the Census streets with those names. An affine fit
     from about 140 such words is good to a few meters,
  3. takes every Linden row of the county street list (the Board of Elections' list), finds
     its houses in the Census address ranges, and gives each side of each block the district
     its middle is in, 25 meters back from the street. The DPW's lines follow streets, so a
     side of a block is in one district; 25 meters keeps clear of a line drawn down the
     middle of a street (Roselle St: odd numbers district 3, even district 4).

The map says in a box that Raritan Road and Hillcrest Terrace are District 10, although
they are drawn inside District 9. Recycle Coach agrees with the box (checked 2026-11-19).

Marked to check (Needs_Check):
  - a block side whose middle (25 m back) is within 15 meters of another district, or whose
    ends (a fifth of the way in) are in different districts,
  - houses more than 60 meters outside every district area (the industrial east side),
    given the nearest one,
  - a street name the county list spells with another ending ("LIBERTY ST" for LIBERTY AVE),
  - house numbers the Census does not have: they get the district of the nearest Census
    number on the same street,
  - a street the DPW line runs down, both sides, unless Recycle Coach confirmed the split
    (SPLIT_STREETS_CHECKED) or showed otherwise (RECYCLE_COACH_BLOCKS: N Stiles St),
  - streets the Census does not have: the district most other houses in the same ward and
    election district are in, unless Recycle Coach was asked (RECYCLE_COACH_STREETS).
Newark Ave is in the county list under Linden but is not in Linden (NOT_LINDEN).

Checked against Recycle Coach on 2026-11-19 in three rounds, 41 addresses (see tests/test_linden.py).
The first 20 also chose SETBACK. Rounds two and three found Jones Pl and Donald Ave (not on
the Census map), N Stiles St (not split by side) and Newark Ave (not in Linden).

This is a developer tool, it is not used by the running website. It needs the `pyshp`
package, `pdftocairo` and `pdftotext` (poppler-utils), the DPW map and the Census file
named in tools/build_kenilworth.py:

    python3 tools/build_linden.py DPW-Collection-District.pdf <addrfeat folder>/tl_2025_34039_addrfeat
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
OUT_FILE = os.path.join(TOP, 'data', 'linden.csv')
ZIP_CODE = '07036'

#Fill color of each district on the DPW map (as pdftocairo writes it)
DISTRICT_COLORS = {
    '98.429871%, 75.68512%, 98.429871%': '1', '98.429871%, 83.920288%, 25.489807%': '2',
    '97.253418%, 92.547607%, 70.587158%': '3', '68.234253%, 91.763306%, 97.645569%': '4',
    '90.979004%, 86.273193%, 73.332214%': '5', '79.998779%, 71.37146%, 80.783081%': '6',
    '67.842102%, 82.743835%, 65.489197%': '7', '96.861267%, 76.861572%, 59.214783%': '8',
    '78.430176%, 78.430176%, 77.645874%': '9', '87.057495%, 85.881042%, 78.822327%': '10',
}
#The map's own note: drawn inside District 9, but District 10
NOTE_STREETS = {'RARITAN RD': '10', 'HILLCREST TER': '10'}

#Streets the Census map does not have, checked in Recycle Coach: street -> (district, house
#number checked). Rows within 20 numbers of the checked house are not marked to check.
RECYCLE_COACH_STREETS = {
    'JONES PL': ('1', 112),      # 112 and 230 Jones Pl are District 1 (2026-11-19)
    'DONALD AVE': ('8', 183),    # 183 Donald Ave is District 8 (2026-11-19)
}

#Where the DPW line runs down a street, the map cannot say which side each house counts
#on. Streets where Recycle Coach showed that the two sides really are in different
#districts (2026-11-19): Roselle St (709 is 3, 1110 is 4), Dewitt Ter (odd 10, even 9),
#Park Ave (305 is 5, 638 is 8), W Curtis St (25 is 2, 206 is 1). On other such streets
#both sides are marked to check.
SPLIT_STREETS_CHECKED = {'ROSELLE ST', 'DEWITT TER', 'PARK AVE', 'W CURTIS ST'}
#Blocks where Recycle Coach showed the line is NOT down the street:
#street -> [(side, low, high, district, house checked)]
RECYCLE_COACH_BLOCKS = {
    #1021 (odd) and 1100 (even) N Stiles St are both District 1; the map splits it by side
    'N STILES ST': [('E', 1000, 1199, '1', 1100)],
}

#In the county list under Linden, but not in Linden: Linden has no Newark Ave. The Census
#has a 718 Newark Ave in Kenilworth (07033), Elizabeth (07208) and Westfield (07090), 3 to
#6 km away, and Recycle Coach does not know it in Linden (2026-11-19). Left out.
NOT_LINDEN = {'NEWARK AVE'}

#Meters: how far back from the street a block side is placed, how close another
#district may be before it is checked, how far the nearest district may be
SETBACK = 25
NEAR = 15
FAR = 400
#Inside the white circles behind the district numbers, or just off the edge of the drawing
EDGE = 60

#Census coordinates are turned into meters around this point
LAT0, LON0 = 40.63, -74.25
KX = 111000 * math.cos(math.radians(LAT0))
KY = 111000

#Words on the map that are not (only) a Linden street name
NOT_STREET_WORDS = {'AVE', 'AVENUE', 'STREET', 'PLACE', 'ROAD', 'TERR', 'TERRACE', 'NORTH', 'SOUTH', 'EAST',
                    'WEST', 'LANE', 'COURT', 'DRIVE', 'CIRCLE', 'PARK', 'LINDEN', 'CITY', 'LINE', 'RAILROAD',
                    'ROUTE', 'SCHOOL', 'RIVER', 'CREEK', 'UNION', 'COUNTY', 'HIGH', 'WARD', 'CENTER', 'STATE',
                    'TOWNSHIP', 'BOROUGH', 'ROSELLE', 'RAHWAY', 'ELIZABETH', 'CLARK', 'CARTERET', 'WINFIELD',
                    'CRANFORD', 'ISLAND'}


def to_meters(lon, lat):
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


#----- The DPW map -----

def read_map(pdf):
    """({district: [triangle in page points]}, [(word, page point)])."""
    with tempfile.TemporaryDirectory() as folder:
        svg_path = os.path.join(folder, 'map.svg')
        words_path = os.path.join(folder, 'words.html')
        subprocess.run(['pdftocairo', '-svg', pdf, svg_path], check=True)
        subprocess.run(['pdftotext', '-bbox', pdf, words_path], check=True)
        with open(svg_path, encoding='utf-8') as handle:
            svg = handle.read()
        with open(words_path, encoding='utf-8') as handle:
            words_html = handle.read()

    areas = collections.defaultdict(list)
    path = re.compile(r'<path[^>]*?fill="rgb\(([^)]*)\)"[^>]*?d="([^"]*)"(?:[^>]*?transform="matrix\(([^)]*)\)")?')
    for color, d, matrix in path.findall(svg):
        if color not in DISTRICT_COLORS:
            continue
        #SVG matrix(a, b, c, d, e, f): x' = a x + c y + e, y' = b x + d y + f
        a, b, c, dd, e, f = [float(v) for v in matrix.split(',')] if matrix else (1, 0, 0, 1, 0, 0)
        tokens = re.findall(r'[MLCZ]|-?[\d.]+', d)
        if 'C' in tokens:
            sys.exit('A district area has curves; this tool only reads straight lines')
        shape, n = [], 0
        while n < len(tokens):
            token = tokens[n]
            if token in 'ML':
                x, y = float(tokens[n + 1]), float(tokens[n + 2])
                if token == 'M' and shape:
                    areas[DISTRICT_COLORS[color]].append(shape)
                    shape = []
                shape.append((a * x + c * y + e, b * x + dd * y + f))
                n += 3
            else:
                if token == 'Z' and shape:
                    areas[DISTRICT_COLORS[color]].append(shape)
                    shape = []
                n += 1
        if shape:
            areas[DISTRICT_COLORS[color]].append(shape)
    if sorted(areas, key=int) != [str(n) for n in range(1, 11)]:
        sys.exit('Did not find all ten district colors on the map: %s' % sorted(areas))

    words = []
    for x0, y0, x1, y1, text in re.findall(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]+)<', words_html):
        words.append((re.sub(r'[^A-Z]', '', text.upper()), ((float(x0) + float(x1)) / 2, (float(y0) + float(y1)) / 2)))
    return areas, words


def nearest_on(point, lines):
    """(distance, nearest point) from a point to a set of lines."""
    best = (math.inf, None)
    for line in lines:
        for a, b in zip(line, line[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = dx * dx + dy * dy
            t = 0 if length == 0 else max(0, min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length))
            q = (a[0] + t * dx, a[1] + t * dy)
            d = math.dist(point, q)
            if d < best[0]:
                best = (d, q)
    return best


def fit_affine(pairs):
    """Least squares (x, y) -> (X, Y): ((a, b, c), (d, e, f)) with X = ax + by + c, Y = dx + ey + f."""
    m = [[0.0] * 3 for _ in range(3)]
    rx, ry = [0.0] * 3, [0.0] * 3
    for (x, y), (X, Y) in pairs:
        v = (x, y, 1.0)
        for i in range(3):
            rx[i] += v[i] * X
            ry[i] += v[i] * Y
            for j in range(3):
                m[i][j] += v[i] * v[j]

    def solve(rhs):
        rows = [row[:] + [r] for row, r in zip(m, rhs)]
        for i in range(3):
            pivot = max(range(i, 3), key=lambda r: abs(rows[r][i]))
            rows[i], rows[pivot] = rows[pivot], rows[i]
            if abs(rows[i][i]) < 1e-12:
                return None
            for r in range(3):
                if r != i:
                    factor = rows[r][i] / rows[i][i]
                    rows[r] = [p - factor * q for p, q in zip(rows[r], rows[i])]
        return tuple(rows[i][3] / rows[i][i] for i in range(3))

    gx, gy = solve(rx), solve(ry)
    return None if gx is None or gy is None else (gx, gy)


def apply(transform, p):
    (a, b, c), (d, e, f) = transform
    return (a * p[0] + b * p[1] + c, d * p[0] + e * p[1] + f)


def line_up(words, street_lines):
    """The page -> meters transform: map words on the Census streets of the same name."""
    usable = [(w, p) for w, p in words if len(w) >= 4 and w not in NOT_STREET_WORDS and w in street_lines]
    middle = {w: (sum(x for line in lines for x, _ in line) / sum(len(line) for line in lines),
                  sum(y for line in lines for _, y in line) / sum(len(line) for line in lines))
              for w, lines in street_lines.items()}
    #A rough fit first, from three words at a time (most words are in the map's street
    #index, far from their street, so most samples are wrong)
    rng = random.Random(1)
    best = (0, None)
    for _ in range(3000):
        transform = fit_affine([(p, middle[w]) for w, p in rng.sample(usable, 3)])
        if transform is None:
            continue
        (a, b, _), (d, e, _) = transform
        if not 0.2 < math.sqrt(abs(a * e - b * d)) < 5:
            continue
        hits = sum(1 for w, p in usable if math.dist(apply(transform, p), middle[w]) < 400)
        if hits > best[0]:
            best = (hits, transform)
    transform = best[1]
    #Then pull the words onto their streets, tighter each round
    for tolerance in (300, 150, 80, 50, 35, 25, 25, 25):
        pairs = []
        for w, p in usable:
            d, q = nearest_on(apply(transform, p), street_lines[w])
            if d < tolerance:
                pairs.append((p, q))
        transform = fit_affine(pairs)
    errors = sorted(nearest_on(apply(transform, p), street_lines[w])[0] for w, p in usable)
    on_street = [e for e in errors if e < 25]
    print('Map lined up with the Census streets: %d words within 25 m, median %.1f m'
          % (len(on_street), on_street[len(on_street) // 2]))
    if len(on_street) < 80:
        sys.exit('Too few map words matched their streets; the map has changed?')
    return transform


class Districts:
    """The district areas in meters, and point lookups."""

    def __init__(self, areas, transform):
        self.items = []
        for district, shapes in areas.items():
            for shape in shapes:
                if len(shape) < 3:
                    continue
                points = [apply(transform, p) for p in shape]
                xs, ys = [x for x, _ in points], [y for _, y in points]
                self.items.append((min(xs), min(ys), max(xs), max(ys), district, points))

    @staticmethod
    def inside(points, p):
        x, y = p
        found = False
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                found = not found
        return found

    def around(self, p, radius):
        """{district: distance in meters} for the districts within radius of p (0 = inside)."""
        found = {}
        for x0, y0, x1, y1, district, points in self.items:
            if not (x0 - radius <= p[0] <= x1 + radius and y0 - radius <= p[1] <= y1 + radius):
                continue
            if self.inside(points, p):
                d = 0
            else:
                d = nearest_on(p, [points + points[:1]])[0]
            if d <= radius:
                found[district] = min(found.get(district, math.inf), d)
        return found


#----- Census houses and the county list -----

def read_census(path):
    """Linden from the Census: ({name: [block side]}, {map word: [street lines]}).

    A block side is (low, high, parity, points in meters, is left side)."""
    sides = collections.defaultdict(list)
    street_lines = collections.defaultdict(list)
    for item in shapefile.Reader(path).iterShapeRecords():
        record = item.record.as_dict()
        if ZIP_CODE not in (record['ZIPL'], record['ZIPR']):
            continue
        points = [to_meters(x, y) for x, y in item.shape.points]
        full_name = (record['FULLNAME'] or '').upper()
        for word in re.findall(r'[A-Z]{4,}', full_name):
            street_lines[word].append(points)
        name = normalize_street(full_name)
        for side in 'LR':
            low, high = record[side + 'FROMHN'], record[side + 'TOHN']
            if record['ZIP' + side] != ZIP_CODE or not (low.isdigit() and high.isdigit()):
                continue
            low, high = sorted((int(low), int(high)))
            sides[name].append((low, high, 'E' if low % 2 == 0 else 'O', points, side == 'L'))
    return sides, street_lines


def along(points, fraction, left, setback):
    """The point `fraction` of the way along a street line, `setback` meters to one side."""
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


def read_county():
    """Linden rows of the county list: [(name, low, high, side, ward, election district)]."""
    rows = []
    with open(COUNTY_FILE, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            if row['Municipality'] == 'LINDEN':
                rows.append((normalize_street(row['Street_Name']), int(row['Low_Range']), int(row['High_Range']),
                             row['Side'], row['Ward'], row['District']))
    return rows


def lookup_names(name, census):
    """(Census names to look a county list street up under, whether the match is only a guess).

    The county list writes "MC CANDLESS ST", "E 13 TH", "W ST GEORGES AVE"; the Census
    "MCCANDLESS ST", "E 13TH ST", "W SAINT GEORGES AVE"."""
    tidy = re.sub(r'\b(\d+) (ST|ND|RD|TH)\b', r'\1\2', name)
    tidy = re.sub(r'\b(MC|MAC) ', r'\1', tidy)
    tidy = re.sub(r'^((?:[NSEW] )?)ST ', r'\1SAINT ', tidy).replace('SAINT GEORGE AVE', 'SAINT GEORGES AVE')
    tidy = re.sub(r' (APT|UNIT)\b.*$', '', tidy).replace(' RR ', ' RAILROAD ')
    tries = [name, tidy, re.sub(r'\b(MC|MAC)(?=[A-Z])', r'\1 ', tidy), tidy + ' ST', tidy + ' CT']
    words = tidy.split()
    if len(words) >= 3 and words[0] in ('E', 'W', 'N', 'S'):
        tries.append(' '.join(words[1:]))
    else:
        tries += [d + ' ' + tidy for d in ('E', 'W', 'N', 'S')]
    names = []
    for n in tries:
        if n in census and n not in names:
            names.append(n)
    if names:
        return names, False
    #The same name with another ending ("LIBERTY ST" is "LIBERTY AVE"), when there is only one
    base = ' '.join(words[:-1]) if len(words) > 1 else tidy
    same_base = [n for n in census if ' '.join(n.split()[:-1]) == base]
    if base and len(same_base) == 1:
        return same_base, True
    return [], False


def place_block_side(block, districts, street=''):
    """(district, check, why) for one Census block side."""
    low, high, parity, points, left = block
    for b_side, b_low, b_high, b_district, _ in RECYCLE_COACH_BLOCKS.get(street, []):
        if b_side == parity and b_low <= low and high <= b_high:
            return b_district, False, ''
    around = districts.around(along(points, 0.5, left, SETBACK), FAR)
    if not around:
        return None, True, 'far from every district'
    district = min(around, key=around.get)
    if around[district] > 0:
        alone = all(d == district or distance > around[district] + 100 for d, distance in around.items())
        if around[district] > EDGE or not alone:
            return district, True, 'outside the districts, nearest %s at %d m' % (district, around[district])
        return district, False, ''
    others = sorted(d for d, distance in around.items() if d != district and distance < NEAR)
    if others:
        return district, True, 'within %d m of district %s' % (NEAR, '/'.join(others))
    ends = {min(a, key=a.get) for a in (districts.around(along(points, f, left, SETBACK), FAR) for f in (0.2, 0.8)) if a}
    if ends - {district}:
        return district, True, 'block ends in district %s' % '/'.join(sorted(ends - {district}))
    across = districts.around(along(points, 0.5, not left, SETBACK), FAR)
    if across and min(across, key=across.get) != district and street not in SPLIT_STREETS_CHECKED:
        return district, True, 'the line runs down the street, district %s across it' % min(across, key=across.get)
    return district, False, ''


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    areas, words = read_map(sys.argv[1])
    census, street_lines = read_census(sys.argv[2])
    districts = Districts(areas, line_up(words, street_lines))
    county = read_county()

    out, notes, unplaced = [], [], []
    placed = collections.defaultdict(collections.Counter)
    for name, low, high, side, ward, election in county:
        names, guessed_name = lookup_names(name, census)
        out_name = names[0] if names else name
        if name in NOT_LINDEN:
            notes.append('left out  %s %d-%d: not in Linden' % (name, low, high))
            continue
        if out_name in NOTE_STREETS:
            out.append((out_name, low, high, side, NOTE_STREETS[out_name], False))
            placed[(ward, election)][NOTE_STREETS[out_name]] += 1
            continue
        found = []
        for n in names:
            found = [b for b in census[n] if b[0] <= high and low <= b[1] and (side == 'B' or side == b[2])]
            if found:
                out_name = n
                break
        if found:
            pieces = []
            for block in found:
                district, check, why = place_block_side(block, districts, out_name)
                pieces.append((max(low, block[0]), min(high, block[1]), block[2], district, check, why))
                if why:
                    notes.append('check  %s %d-%d (Census %d-%d): %s' % (out_name, low, high, block[0], block[1], why))
            check = guessed_name or any(p[4] for p in pieces)
            if len({p[3] for p in pieces}) == 1:
                out.append((out_name, low, high, side, pieces[0][3], check))
                placed[(ward, election)][pieces[0][3]] += 1
            else:
                for p_low, p_high, parity, district, p_check, _ in pieces:
                    out.append((out_name, p_low, p_high, parity if side == 'B' else side, district, p_check or guessed_name))
                    placed[(ward, election)][district] += 1
                notes.append('split  %s %d-%d: %s' % (out_name, low, high,
                                                     ', '.join('%d-%d %s' % (p[0], p[1], p[3]) for p in pieces)))
            continue
        if names:
            #A house number the Census does not have: the nearest one on the same street
            candidates = [(min(abs(low - b[0]), abs(low - b[1])), b) for n in names for b in census[n]]
            gap, nearest = min(candidates, key=lambda c: c[0])
            district, _, _ = place_block_side(nearest, districts, out_name)
            if district:
                out.append((out_name, low, high, side, district, True))
                placed[(ward, election)][district] += 1
                notes.append('near   %s %d-%d: district %s, from Census %d-%d' % (out_name, low, high, district,
                                                                                 nearest[0], nearest[1]))
                continue
        unplaced.append((name, low, high, side, ward, election))

    #Streets not on the Census map: the district most others in their ward and election district are in
    for name, low, high, side, ward, election in unplaced:
        if name in RECYCLE_COACH_STREETS:
            district, checked = RECYCLE_COACH_STREETS[name]
            near_checked = low - 20 <= checked <= high + 20
            out.append((name, low, high, side, district, not near_checked))
            notes.append('coach  %s %d-%d: district %s (Recycle Coach, %d)' % (name, low, high, district, checked))
            continue
        counts = placed[(ward, election)]
        if not counts:
            notes.append('skip   %s %d-%d: not on the Census map, nothing else in ward %s district %s'
                         % (name, low, high, ward, election))
            continue
        district = counts.most_common(1)[0][0]
        out.append((name, low, high, side, district, True))
        notes.append('guess  %s %d-%d: district %s, from ward %s election district %s %s'
                     % (name, low, high, district, ward, election, dict(counts)))

    rows = sorted(set(out), key=lambda r: (r[0], r[1], r[2], r[3]))
    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['Municipality', 'Street_Name', 'Low_Range', 'High_Range', 'Side', 'ZIP', 'Zone', 'Needs_Check'])
        for name, low, high, side, district, check in rows:
            writer.writerow(['LINDEN', name, low, high, side, ZIP_CODE, district, 'Y' if check else ''])
    print('\n'.join(notes))
    by_district = collections.Counter(r[4] for r in rows)
    print('%d rows written to %s, %d to check; by district: %s'
          % (len(rows), os.path.normpath(OUT_FILE), sum(1 for r in rows if r[5]),
             dict(sorted(by_district.items(), key=lambda kv: int(kv[0])))))


if __name__ == '__main__':
    main()
