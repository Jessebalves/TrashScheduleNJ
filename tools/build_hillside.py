#!/usr/bin/env python3
"""Build data/hillside.csv: every Hillside address range and its collection district.

Hillside collects household trash in two districts, and the township prints the
streets of each district on its solid waste calendar (2026-2027 calendar,
https://hillsidenj.us/external-6494, and the older "Solid Waste & Recycling
District Schedule"). This tool takes every Hillside address range from the
county street list (data/reference/union_county_street_list_2025.csv) and gives
it the district of its street.

Four streets are split between the districts at a cross street. The house
number where each split falls was read from the US Census address ranges for
Union County (TIGER 2025 ADDRFEAT), see SPLITS below.

Streets that are not on the township's lists, or that the lists do not settle,
get a "Y" in the Needs_Check column, and the website asks the visitor to
confirm with the DPW.

This is a developer tool, it is not used by the running website. Run it with:

    python3 tools/build_hillside.py
"""
import csv
import os
import sys

TOP = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, TOP)

from address_lookup import normalize_street  # noqa: E402

COUNTY_FILE = os.path.join(TOP, 'data', 'reference', 'union_county_street_list_2025.csv')
OUT_FILE = os.path.join(TOP, 'data', 'hillside.csv')
ZIP_CODE = '07205'

#District #1, Monday & Thursday. Spelled the way the county list spells them.
DISTRICT_1 = """
ACME PL, ARTHUR ST, AVY ST, BAKER ST, BALTIMORE AVE, BANK ST, BAUER TER, BEECHWOOD PL,
BLACKBURN RD, BOSTON AVE, BRADFORD RD, BRIGHT ST, BROADWAY, CEDAR ST, CENTRAL AVE, CHESTER ST,
CHURCH ST, CLIFFORD ST, COE AVE, CONANT ST, CRANN ST, CRYSTAL TER, DENMAN PL, DOD PL, ELMER PL,
EVANS TERMINAL, EXETER WAY, FAIRBANKS ST, FAIRVIEW PL, FIRST ST, FITZPATRICK ST, FRANCES PL,
GATEWAY ST, GEORGIAN CT, GERTRUDE ST, GREENWOOD TER, GURD AVE, HALL CT, HARTLEY TER, HAVILAND DR,
HERBERT AVE, HOLLYWOOD AVE, HOWARD ST, HURDEN ST, IRVINGTON AVE, JAMES ST, JEROME AVE,
JOHN GLENN DR, KAY LN, KING ST, LAKEVIEW DR, LELAND PL, LINWOOD PL, LIVINGSTON RD, LOOKER ST,
MADING TER, MALDEN TER, MARINE TER, MILLARD AVE, MIRIAM PL, MYRTLE ST, NORTH AVE, NOTTINGHAM WAY,
OAKWOOD AVE, OGDEN WAY, PARK ST, PENNSYLVANIA AVE, PLYMOUTH RD, PROSPECT ST, QUEEN CT, RACE ST,
REVERE DR, RIDGEWAY AVE, RIVERSIDE DR, ROANOKE AVE, ROBERT ST, RYAN ST, SALEM AVE, SANFORD AVE,
SCHLEIFER RD, SECOND ST, SILVER AVE, S BRIGHT ST, S LONG AVE, S MYRTLE ST, S STATE ST,
ST LOUIS AVE, STATE ST, STERNER RD, STONE ST, SUPERIOR ST, SURREY RD, THIRD ST, THOMAS ST,
TRINITY PL, UNION AVE, VALLEY VIEW RD, VINE ST, VIRGINIA ST, VOORHEES ST, WARWICK RD, W KING ST,
WESTMINSTER AVE, WHITE ST, WILDER ST, WILLIAM ST, WINCHESTER AVE, WINDSOR WAY, WOODRUFF AVE,
WOODRUFF PL
"""

#District #2, Tuesday & Friday
DISTRICT_2 = """
ALDINE ST, ARNOLD ST, BAILEY AVE, BAYVIEW AVE, BELLEVIEW TER, BERGEN ST, BERNARD TER, BOA PL,
BOND ST, BUCHANAN ST, BURNETT ST, CENTER ST, CHAPMAN ST, CHESTNUT AVE, CLARK ST, CLINTON PL,
COLUMBIA AVE, COLUMBIA PL, COMPTON PL, COMPTON TER, CONKLIN AVE, CORNELL PL, CRESCENT AVE,
DOREMUS PL, DORER AVE, EASTERN PKWY, EMERSON LN, FABYAN PL, FAIRCHILD PL, FIELD PL, FLORENCE AVE,
FRANKLIN ST, GARDNER ST, GLENWOOD AVE, GRUMMAN AVE, HARDING TER, HARVARD AVE, HIAWATHA AVE,
HIGHLAND AVE, HILLDALE PL, HILLSIDE AVE, HOFFMAN PL, ITASKA ST, JOHN ST, LEHIGH PL, LEHIGH ST,
LEO ST, LESLIE ST, LOCUST AVE, MAPLE AVE, MCLEAN PL, MCMICHAEL PL, MEMORIAL DR, MERTZ AVE,
MOHAWK ST, MONTGOMERY ST, MORRIS PL, MUNDET PL, MUNN AVE, NEW YORK PL, NORMAN ST, N UNION AVE,
OAKLAND TER, ORCHARD TER, PARKVIEW TER, PAUL ST, PRINCETON AVE, PURCE ST, QUABECK AVE, RAMSEY AVE,
ROOSEVELT DR, US HIGHWAY 22, RUTGERS AVE, SAGER PL, SCHLEY ST, SHELTON TER, SPRING ST,
STANLEY TER, STOCKTON AVE, SUMMER AVE, SUMMIT AVE, SWEETLAND AVE, TILLMAN ST, WAINWRIGHT ST,
W MERTZ AVE, W SHELTON TER, WILLIAMSON AVE, WINANS AVE, WOLF PL, WYNDMOOR AVE, YALE AVE, YOUNG AVE
"""

#Streets split between the districts: (first house number of the next part, district, check)
#for each part, from the lowest numbers up.
SPLITS = {
    #District 1 from Gurd Ave to Liberty Ave, District 2 from Liberty Ave to Ramsey Ave.
    #The block ending at Liberty Ave is 280-298, the next one starts at 300.
    'BLOY ST': [(300, '1', False), (None, '2', False)],
    #District 1 from Conant St to Long Ave, District 2 from Long Ave to Summit Ave.
    #The block ending at Long Ave is 1307-1349, the next one starts at 1350.
    'LIBERTY AVE': [(1350, '1', False), (None, '2', False)],
    #District 1 from Pennsylvania Ave to Liberty Ave, District 2 from Liberty Ave to Bloy St.
    #The block ending at Liberty Ave is 256-299, the next one starts at 300.
    'LONG AVE': [(300, '1', False), (None, '2', False)],
    #District 1 from the Elizabeth line to Hillside Ave, District 2 from Hillside Ave to
    #Newark. Hillside Ave comes closest to N Broad St on the 1400-1433 block, so that
    #block is District 1 and marked to check.
    'N BROAD ST': [(1400, '1', False), (1435, '1', True), (None, '2', False)],
}

#Streets in the county list that are on neither district list. They are given the
#district of the streets around them (Census map) and marked to check.
NOT_LISTED = {
    'LIBERTY CT': '1',   #off Liberty Ave and Bloy St, between Herbert Ave and Columbia Ave
    'MASTERS SQ': '1',   #between Exeter Way and Haviland Dr
}

#Buchanan St is in District 2 on the township's older list. The 2026-2027 calendar
#lists it in District 2 and also prints "Broadway/Buchanan St." in District 1.
CHECK = {'BUCHANAN ST'}

#Streets on the district lists that the county list (made from the voter rolls) does
#not have. Their house numbers are from the Census address ranges (TIGER 2025 ADDRFEAT).
#Bergen St, Fabyan Pl, Kay Ln and Mohawk St have no house numbers in either source.
EXTRA = [
    ('FIRST ST', 100, 199), ('SECOND ST', 100, 199), ('CLIFFORD ST', 100, 299), ('HALL CT', 1, 99),
    ('ARNOLD ST', 500, 599), ('BURNETT ST', 100, 198), ('CHESTNUT AVE', 1301, 1499),
    ('EMERSON LN', 300, 399), ('GARDNER ST', 400, 499), ('HOFFMAN PL', 2, 198),
    ('MEMORIAL DR', 200, 299), ('MONTGOMERY ST', 1, 99), ('MUNDET PL', 400, 499),
    ('RAMSEY AVE', 600, 799), ('STOCKTON AVE', 500, 699), ('W SHELTON TER', 1, 99),
]

#County spellings that are typos or variants of a street above
COUNTY_NAMES = {
    'N BOARD ST': 'N BROAD ST',
    'BROAD ST': 'N BROAD ST',
    'GRUMMAN AVE APT 1': 'GRUMMAN AVE',
    'HARDING TERRACE': 'HARDING TER',
    'MC LEAN PL': 'MCLEAN PL',
    'MC MICHAEL PL': 'MCMICHAEL PL',
    'SAINT LOUIS AVE': 'ST LOUIS AVE',
    'US 22': 'US HIGHWAY 22',
    '3RD ST': 'THIRD ST',
}

#County rows that are not streets
SKIP = {'PO BOX', '1 2 BROADWAY'}


def street_list(text):
    return {normalize_street(name) for name in text.replace('\n', ' ').split(',') if name.strip()}


def parts(street, low, high, side):
    """Cut one county range where its street changes district. Yields (low, high, zone, check)."""
    if street in SPLITS:
        start = low
        for next_start, zone, check in SPLITS[street]:
            end = high if next_start is None else min(high, next_start - 1)
            if start <= end:
                yield start, end, zone, check
            if next_start is not None:
                start = max(start, next_start)
        return
    if street in NOT_LISTED:
        yield low, high, NOT_LISTED[street], True
        return
    zone = '1' if street in ONE else '2'
    yield low, high, zone, street in CHECK


ONE = street_list(DISTRICT_1)
TWO = street_list(DISTRICT_2)


def main():
    both = ONE & TWO
    if both:
        sys.exit('In both districts: ' + ', '.join(sorted(both)))
    rows, unknown = [], set()
    with open(COUNTY_FILE, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            if row['Municipality'] != 'HILLSIDE' or row['Street_Name'] in SKIP:
                continue
            street = COUNTY_NAMES.get(row['Street_Name'], row['Street_Name'])
            key = normalize_street(street)
            if key not in ONE | TWO and key not in SPLITS and key not in NOT_LISTED:
                unknown.add(street)
                continue
            for low, high, zone, check in parts(key, int(row['Low_Range']), int(row['High_Range']), row['Side']):
                rows.append((street, low, high, row['Side'], zone, 'Y' if check else ''))
    if unknown:
        sys.exit('No district for: ' + ', '.join(sorted(unknown)))
    in_county = {normalize_street(r[0]) for r in rows}
    for street, low, high in EXTRA:
        key = normalize_street(street)
        if key in in_county:
            continue    #the county list has it now, use that
        for low, high, zone, check in parts(key, low, high, 'B'):
            rows.append((street, low, high, 'B', zone, 'Y' if check else ''))

    rows = sorted(set(rows), key=lambda r: (r[0], r[1], r[2], r[3]))
    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['Municipality', 'Street_Name', 'Low_Range', 'High_Range', 'Side', 'ZIP', 'Zone', 'Needs_Check'])
        for street, low, high, side, zone, check in rows:
            writer.writerow(['HILLSIDE', street, low, high, side, ZIP_CODE, zone, check])
    print(f'{len(rows)} rows written to {os.path.normpath(OUT_FILE)}')
    listed = (ONE | TWO) - {normalize_street(r[0]) for r in rows}
    if listed:
        print('On the township lists, but no house numbers known:', ', '.join(sorted(listed)))


if __name__ == '__main__':
    main()
