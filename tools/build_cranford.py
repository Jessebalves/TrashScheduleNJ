#!/usr/bin/env python3
"""Build data/cranford.csv: every Cranford Township address range and its recycling section.

Cranford does not collect household trash (residents hire private haulers). The township's
recycling contractor (Giordano) picks up every other week in four sections: North Side
Monday, North Side Tuesday, South Side Monday, South Side Tuesday (zones NM, NT, SM, ST).

The township's "2026 Curbside Recycling Zones and Street Names" list is typed into
data/reference/cranford_2026_sections.csv. Most streets are in one section. A street that
is in two (Casino Ave, Orange Ave, Springfield Ave, ...) is cut at its cross streets; the
house numbers of those cross streets were read off the US Census address ranges and are
written into SPLIT_STREETS below with the list's own words.

The house numbers are the county street list's Cranford rows
(data/reference/union_county_street_list_2025.csv). Listed streets the county list does
not have get the Census address ranges instead.

Marked to check (Needs_Check):
  - parts of a split street the list does not cover (see SPLIT_STREETS),
  - streets that are not on the list: they get the section most other streets in the
    same ward and election district have.

This is a developer tool, it is not used by the running website. It needs the
`pyshp` package and the Census file named in tools/build_kenilworth.py:

    python3 tools/build_cranford.py <addrfeat folder>/tl_2025_34039_addrfeat
"""
import collections
import csv
import os
import sys

import shapefile  # pip install pyshp

TOP = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, TOP)

from address_lookup import normalize_street  # noqa: E402

COUNTY_FILE = os.path.join(TOP, 'data', 'reference', 'union_county_street_list_2025.csv')
SECTIONS_FILE = os.path.join(TOP, 'data', 'reference', 'cranford_2026_sections.csv')
OUT_FILE = os.path.join(TOP, 'data', 'cranford.csv')
ZIP_CODE = '07016'

SECTION_IDS = {'North Side - Monday': 'NM', 'North Side - Tuesday': 'NT',
               'South Side - Monday': 'SM', 'South Side - Tuesday': 'ST'}

#The street names in data/cranford.csv are the Census spellings. Other spellings, from the
#township's list or the county list -> that name. (towns/cranford.json has the same list
#in "street_names" for visitors who type them.)
OTHER_NAMES = {
    'CHIPPEWA WAY': 'CHIPPAWA WAY',
    'HEATHERMEAD PL': 'HEATHERMEADE PL',
    'HENRICH ST': 'HEINRICH ST',
    'LA CORTE TER': 'LACORTE TER',
    'LA SALLE AVE': 'LASALLE AVE',
    'MACARTHUR ST': 'MACARTHUR AVE',
    'RALIEGH AVE': 'RALEIGH AVE',
    'WOODSHOLE RD': 'WOODS HOLE RD',
    'EDWARD PL': 'EDWARD ST',
    'BALMIERE ROAD N': 'N BALMIERE RD',
    'BALMIERE ROAD S': 'S BALMIERE RD',
    'BALMIERE RD N': 'N BALMIERE RD',
    'BALMIERE RD S': 'S BALMIERE RD',
    'LENHOME DR N': 'N LENHOME DR',
    'LENHOME DR S': 'S LENHOME DR',
    'LINCOLN AVENUE EAST': 'LINCOLN AVE E',
    'LINCOLN AVENUE WEST': 'LINCOLN AVE W',
    'E LINCOLN AVE': 'LINCOLN AVE E',
    'LINCOLN E': 'LINCOLN AVE E',
    'LINCOLN PARK EAST': 'LINCOLN PARK E',
    'SOUTH AVE': 'S AVE',
    'NORTH UNION AVE': 'N UNION AVE',
    'SOUTH UNION AVE': 'S UNION AVE',
    'WEST END PL': 'W END PL',
    'PARKWAY VILLAGE APARTMENTS': 'PARKWAY VLG',
    'PARKWAY VILLAGE': 'PARKWAY VLG',
    'A PARKWAY VLG': 'PARKWAY VLG',
    'B PARKWAY VLG': 'PARKWAY VLG',
}

#"South Avenue (Entire Street)" is both South Ave E and South Ave W
BOTH_HALVES = {'S AVE': ['S AVE E', 'S AVE W']}

#Streets in two sections, or only partly on the list: (low, high, side, section, check).
#side is 'O' (odd numbers), 'E' (even) or 'B' (both). A row is cut where the ranges change.
#Cross street house numbers from the Census address ranges.
BIG = 99999
SPLIT_STREETS = {
    #NT "From Linden Pl to Riverside Dr", NM "From Linden Pl to Pacific Ave": Linden Pl is at 400
    'CASINO AVE': [(1, 399, 'B', 'NT', False), (400, BIG, 'B', 'NM', False)],
    #NM "Between Eastman & Springfield Ave", NT "Between Springfield & Craig Pl": Springfield Ave at 100
    'CENTRAL AVE': [(1, 99, 'B', 'NM', False), (100, BIG, 'B', 'NT', False)],
    #NM "Between Orange Ave & N Union Ave" (N Union Ave at 1, Orange Ave at 299), NT the rest
    'MANOR AVE': [(1, 298, 'B', 'NM', False), (299, BIG, 'B', 'NT', False)],
    #NT "North Avenue East (Between Springfield Ave. & Carpenter Pl)"; NM also has "North Avenue
    #East/West (Between Springfield Ave down to Lincoln Ave)", which fits North Ave W (it ends at
    #Lincoln Ave). The first block of North Ave E (downtown) could be either
    'N AVE E': [(1, 99, 'B', 'NT', True), (100, BIG, 'B', 'NT', False)],
    #NM "Between Springfield Ave & North Ave E" (North Ave at 1, Springfield Ave at 124),
    #NT "From Linden Pl to Riverside Dr" (Riverside Dr at 200, Linden Pl at 400),
    #NM "Between Linden Pl & Lenox Ave" (Lenox Ave at 599). 124-199 and past Lenox Ave are not listed
    'N UNION AVE': [(1, 123, 'B', 'NM', False), (124, 199, 'B', 'NT', True), (200, 399, 'B', 'NT', False),
                    (400, 599, 'B', 'NM', False), (600, BIG, 'B', 'NM', True)],
    #NT "From Springfield Ave to Craig Pl" (Craig Pl at 416), NM "From Linden Place to Kenilworth
    #Border" (Linden Pl at 411): 411-415 is between the two
    'ORANGE AVE': [(1, 410, 'B', 'NT', False), (411, 415, 'B', 'NT', True), (416, BIG, 'B', 'NM', False)],
    #NT "Between Linden Pl & Riverside Dr", NM "Between Manor Ave & Linden Pl": Linden Pl at 400
    'PROSPECT AVE': [(1, 399, 'B', 'NT', False), (400, BIG, 'B', 'NM', False)],
    #NT "From Orange Ave to N Union Ave" is 500-799 on the Census map; NM "Linden Place" is the rest
    'LINDEN PL': [(1, 499, 'B', 'NM', True), (500, 799, 'B', 'NT', False), (800, BIG, 'B', 'NM', False)],
    #NM "West Side (From Kenilworth Blvd to North Ave)": the odd numbers (Penn Rd, Princeton Rd side).
    #NT "East Side (From Park Dr to North Ave)": the even numbers up to Park Dr (898)
    'SPRINGFIELD AVE': [(1, BIG, 'O', 'NM', False), (1, 898, 'E', 'NT', False), (899, BIG, 'E', 'NT', True)],
    #NM "Between Gallows Hill & Springfield Ave", NT "From Springfield Ave to Crescent Pl": Springfield Ave at 600
    'W END PL': [(1, 599, 'B', 'NM', False), (600, BIG, 'B', 'NT', False)],
    #NT "From Orange Ave to Prospect Ave" (100-299); Orange Ave to Normandie Pl is not listed
    'MAPLE PL': [(1, 299, 'B', 'NT', False), (300, BIG, 'B', 'NT', True)],
    #NM "Tulip Street (#8-35)" (off Orchard St), NT "Tulip Street (Off of Balmiere Pkwy)" (600-799)
    'TULIP ST': [(1, 99, 'B', 'NM', False), (100, BIG, 'B', 'NT', False)],
    #SM "From Rankin to Railroad Track" (the railroad is where Walnut Ave crosses, near 600),
    #ST "From Walnut Ave to Raritan Rd" (600-799)
    'LEXINGTON AVE': [(1, 599, 'B', 'SM', False), (600, BIG, 'B', 'ST', False)],
    #ST "From Walnut Ave to Lincoln Ave E" (1-99), SM "From Lincoln Ave E to Lexington Ave"
    'RETFORD AVE': [(1, 99, 'B', 'ST', False), (100, BIG, 'B', 'SM', False)],
    #ST "Between Lincoln Ave to S Ave" (1-96), SM "Between Lincoln & Fairfield; Between Fairfield & Lexington"
    'S UNION AVE': [(1, 96, 'B', 'ST', False), (97, BIG, 'B', 'SM', False)],
    #ST "From S Ave E to Lincoln Ave E" (South Ave E at 100, Lincoln Ave E at 300), SM "From Lincoln
    #Ave E to Chester Lang Pl" (300-599), ST "From Raritan Rd to Railroads Track" (700-799).
    #North of South Ave E is not listed
    'WALNUT AVE': [(1, 99, 'B', 'ST', True), (100, 299, 'B', 'ST', False), (300, 599, 'B', 'SM', False),
                   (600, BIG, 'B', 'ST', False)],
    #ST "Between Grant & Railroad Bridge; From S Ave E to Winans Ave". North of the railroad
    #(by North Ave E) is not listed
    'CENTENNIAL AVE': [(1, 33, 'B', 'ST', True), (34, BIG, 'B', 'ST', False)],
}


def table_name(name):
    name = normalize_street(name)
    return OTHER_NAMES.get(name, name)


def read_sections():
    """{table street name: section id} for the streets the list has whole."""
    whole = {}
    with open(SECTIONS_FILE, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            name = table_name(row['Street'].replace('North Avenue East/ West', 'North Ave W')
                              .replace('North Avenue East', 'North Ave E'))
            for n in BOTH_HALVES.get(name, [name]):
                if n not in SPLIT_STREETS:
                    whole[n] = SECTION_IDS[row['Section']]
    return whole


def read_county():
    """Cranford rows of the county list: [(name, low, high, side, ward, district)]."""
    rows = []
    with open(COUNTY_FILE, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            if row['Municipality'] == 'CRANFORD' and row['Street_Name'] != 'PO BOX':
                rows.append((table_name(row['Street_Name']), int(row['Low_Range']), int(row['High_Range']),
                             row['Side'], row['Ward'], row['District']))
    return rows


def read_census(path):
    """Census house ranges in Cranford: {name: [(low, high, parity)]}."""
    ranges = collections.defaultdict(list)
    for record in shapefile.Reader(path).iterRecords():
        record = record.as_dict()
        name = table_name(record['FULLNAME'] or '')
        for side in 'LR':
            low, high = record[side + 'FROMHN'], record[side + 'TOHN']
            if record['ZIP' + side] != ZIP_CODE or not (low.isdigit() and high.isdigit()):
                continue
            low, high = sorted((int(low), int(high)))
            ranges[name].append((low, high, 'E' if low % 2 == 0 else 'O'))
    return ranges


def cut(name, low, high, side):
    """A row on a split street cut into [(low, high, side, section, check)]."""
    pieces = []
    for r_low, r_high, r_side, section, check in SPLIT_STREETS[name]:
        if r_side != 'B' and side not in (r_side, 'B'):
            continue
        s_low, s_high = max(low, r_low), min(high, r_high)
        if s_low <= s_high:
            pieces.append((s_low, s_high, r_side if r_side != 'B' else side, section, check))
    return pieces


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    whole = read_sections()
    census = read_census(sys.argv[1])
    county = read_county()

    out, notes, unlisted = [], [], []
    placed = collections.defaultdict(collections.Counter)
    for name, low, high, side, ward, district in county:
        if name in SPLIT_STREETS:
            pieces = cut(name, low, high, side)
        elif name in whole:
            pieces = [(low, high, side, whole[name], False)]
        else:
            unlisted.append((name, low, high, side, ward, district))
            continue
        for piece in pieces:
            out.append((name,) + piece)
            placed[(ward, district)][piece[3]] += 1

    #Listed streets the county list does not have: the Census house numbers
    in_county = {row[0] for row in county}
    for name in sorted(set(whole) - in_county):
        if name not in census:
            notes.append(f'none   {name}: on the list, not in the county list or the Census')
            continue
        for low, high, parity in census[name]:
            out.append((name, low, high, parity, whole[name], False))
        notes.append(f'census {name}: {len(census[name])} Census ranges ({whole[name]})')

    #Streets that are not on the list: the section of their ward and election district
    for name, low, high, side, ward, district in unlisted:
        counts = placed[(ward, district)]
        if not counts:
            notes.append(f'skip   {name} {low}-{high}: not on the list, no other street in ward {ward} district {district}')
            continue
        section = counts.most_common(1)[0][0]
        out.append((name, low, high, side, section, True))
        notes.append(f'guess  {name} {low}-{high}: not on the list, {section} from ward {ward} district {district} {dict(counts)}')

    for name, low, high, side, section, check in out:
        if check and name in SPLIT_STREETS:
            notes.append(f'check  {name} {low}-{high} {side}: {section}, not clearly on the list')

    rows = sorted(set(out))
    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['Municipality', 'Street_Name', 'Low_Range', 'High_Range', 'Side', 'ZIP', 'Zone', 'Needs_Check'])
        for name, low, high, side, section, check in rows:
            writer.writerow(['CRANFORD', name, low, high, side, ZIP_CODE, section, 'Y' if check else ''])
    print('\n'.join(notes))
    zones = collections.Counter(r[4] for r in rows)
    print(f'{len(rows)} rows written to {os.path.normpath(OUT_FILE)}, '
          f'{sum(1 for r in rows if r[5])} to check; by zone: {dict(sorted(zones.items()))}')


if __name__ == '__main__':
    main()
