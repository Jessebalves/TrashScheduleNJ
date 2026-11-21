"""Finds the pickup zone for a street address.

The address table has one row per stretch of a street:

    town, street name, lowest house number, highest house number,
    side (E = even numbers, O = odd numbers, B = both), ZIP code, zone

A zone is whatever the town uses to decide pickup days. In Elizabeth it is the
ward (1 to 6), in Kenilworth it is the garbage route (MON_THU, TUE_FRI, WED_SAT).

Nothing in this file talks to MySQL or to Flask, so it can be tested on its own.
"""
import math

#Every way of writing a street type is turned into one spelling, so that
#"Terrace", "terr." and "TER" all match. The same table is applied to the
#street names from the database, which is why LA and LN can share a spelling.
STREET_TYPES = {
    'STREET': 'ST', 'ST': 'ST', 'STR': 'ST',
    'ROAD': 'RD', 'RD': 'RD',
    'BOULEVARD': 'BLVD', 'BLVD': 'BLVD',
    'AVENUE': 'AVE', 'AVE': 'AVE', 'AV': 'AVE',
    'PLACE': 'PL', 'PL': 'PL',
    'DRIVE': 'DR', 'DR': 'DR',
    'TERRACE': 'TER', 'TER': 'TER', 'TERR': 'TER',
    'COURT': 'CT', 'CT': 'CT',
    'LANE': 'LN', 'LN': 'LN', 'LA': 'LN',
    'CIRCLE': 'CIR', 'CIR': 'CIR',
    'WAY': 'WAY',
    'PARKWAY': 'PKWY', 'PKWY': 'PKWY',
    'PLAZA': 'PLZ', 'PLZ': 'PLZ',
    'MANOR': 'MNR', 'MNR': 'MNR',
    'HIGHWAY': 'HWY', 'HWY': 'HWY',
}

#"North Broad Street" and "N Broad St" are the same street
DIRECTIONS = {'NORTH': 'N', 'SOUTH': 'S', 'EAST': 'E', 'WEST': 'W'}

#"First Avenue" and "1st Ave" are the same street
NUMBER_WORDS = {
    'FIRST': '1ST', 'SECOND': '2ND', 'THIRD': '3RD', 'FOURTH': '4TH',
    'FIFTH': '5TH', 'SIXTH': '6TH', 'SEVENTH': '7TH', 'EIGHTH': '8TH',
    'NINTH': '9TH', 'TENTH': '10TH', 'ELEVENTH': '11TH', 'TWELFTH': '12TH',
}


#Meters in one degree of latitude
METERS_PER_DEGREE = 111000

#On a street that is split between zones, a house number that is not in the
#table is only guessed when it is this close to one that is
MAX_GUESS_GAP = 50


def normalize_street(name):
    """Upper case a street name, drop dots and commas, and use one spelling for each word."""
    words = [word.strip('.,').upper() for word in str(name).split()]
    words = [word for word in words if word]
    if not words:
        return ''
    words = [NUMBER_WORDS.get(word, word) for word in words]
    #A direction is only shortened when it is in front of a longer name, so that
    #"North Ave" and "South St" keep their names
    if len(words) >= 3:
        words[0] = DIRECTIONS.get(words[0], words[0])
    #A direction after the street type, as Cranford writes them: "South Avenue West" and
    #"S Ave W" are the same street
    if len(words) >= 3 and words[-1] in DIRECTIONS and words[-2] in STREET_TYPES:
        words[-1] = DIRECTIONS[words[-1]]
    if len(words) >= 3 and words[-1] in DIRECTIONS.values() and words[-2] in STREET_TYPES:
        words[-2] = STREET_TYPES[words[-2]]
    else:
        words[-1] = STREET_TYPES.get(words[-1], words[-1])
    #"St Georges Ave" and "Saint Georges Ave" (Census), "Mc Kinley St" and "McKinley St"
    #(Google): a name never starts with "Street", so a first ST is Saint
    first = 1 if len(words) >= 3 and words[0] in DIRECTIONS.values() else 0
    if len(words) - first >= 3 and words[first] == 'ST':
        words[first] = 'SAINT'
    if len(words) - first >= 3 and words[first] in ('MC', 'MAC'):
        words[first:first + 2] = [words[first] + words[first + 1]]
    return ' '.join(words)


def normalize_zip(zip_code):
    """Return a 5 digit ZIP code as text, or '' if there is none.

    The Elizabeth county file stored ZIP codes without the leading zero (7208),
    and Google sends "07208-1234" style codes, both become "07208".
    """
    text = str(zip_code or '').strip().split('-')[0]
    if not (text.isascii() and text.isdigit()) or len(text) > 5:
        return ''
    return text.zfill(5)


class AddressBook:
    """All address rows, grouped by town and street so that a lookup is quick."""

    def __init__(self):
        #(town id, street name) -> list of (low, high, side, zip code, zone, needs check)
        self.streets = {}
        self.row_count = 0

    def add(self, town_id, street, low, high, side, zip_code, zone, needs_check=False):
        key = (town_id, normalize_street(street))
        row = (int(low), int(high), str(side).strip().upper(), normalize_zip(zip_code), str(zone).strip(), bool(needs_check))
        self.streets.setdefault(key, []).append(row)
        self.row_count += 1

    def find(self, town_id, house_number, street, zip_code=''):
        """Look up one address.

        Returns None when the street is not in the table for that town.
        Otherwise returns a dictionary:
            zone         the zone id
            needs_check  True when the answer is a best guess the visitor should confirm:
                         the address is on the border between two zones, or the house
                         number is not in the table and its street is split between zones
            zip          the ZIP code of the stretch of street that matched ('' if the table has none)
        """
        rows = self._rows(town_id, normalize_street(street), zip_code)
        if not rows:
            return None

        exact = self._exact(rows, house_number)
        if exact:
            return exact

        side = 'E' if house_number % 2 == 0 else 'O'

        #The house number is not in the table. Lists of house numbers always have
        #gaps, so use the nearest stretch of the same street and say it is a guess.
        #A stretch on the same side of the street wins when two are equally near.
        def distance(row):
            gap = max(row[0] - house_number, house_number - row[1], 0)
            return (gap, 0 if row[2] in (side, 'B') else 1)

        nearest = min(rows, key=distance)
        whole_street_is_one_zone = len({row[4] for row in rows}) == 1
        if not whole_street_is_one_zone and distance(nearest)[0] > MAX_GUESS_GAP:
            return None
        #When the whole street is in one zone the nearest stretch is a safe answer
        sure = whole_street_is_one_zone and not any(row[5] for row in rows)
        return {'zone': nearest[4], 'needs_check': not sure, 'zip': nearest[3]}

    def find_other_spelling(self, town_id, house_number, street, zip_code=''):
        """find() for a street the table writes with or without its N/S/E/W ("W Grove St" is
        "GROVE ST" in parts of the county list). Only used when find() found nothing.

        Without the direction first; with one only when exactly one direction has this house number.
        """
        words = normalize_street(street).split()
        if len(words) >= 3 and words[0] in DIRECTIONS.values():
            return self.find(town_id, house_number, ' '.join(words[1:]), zip_code)
        name = ' '.join(words)
        exact = [found for found in (self._exact(self._rows(town_id, d + ' ' + name, zip_code), house_number)
                                     for d in 'NSEW') if found]
        return exact[0] if len(exact) == 1 else None

    def _rows(self, town_id, name, zip_code):
        """The rows of one street (an already normalized name), only those with a matching ZIP code."""
        rows = self.streets.get((town_id, name), [])
        zip_code = normalize_zip(zip_code)
        if zip_code:
            #A ZIP code that was given has to match. Rows without one match any.
            rows = [row for row in rows if not row[3] or row[3] == zip_code]
        return rows

    @staticmethod
    def _exact(rows, house_number):
        """The answer when the house number itself is in the table, else None."""
        side = 'E' if house_number % 2 == 0 else 'O'
        for low, high, row_side, row_zip, zone, needs_check in rows:
            if low <= house_number <= high and row_side in (side, 'B'):
                return {'zone': zone, 'needs_check': needs_check, 'zip': row_zip}
        return None

    def find_on_split_street(self, town_id, house_number, street, zip_code='', split=None, location=None):
        """Look up an address on a street that has an East and a West part (Roselle's avenues).

        split is the town's "direction_split" setting: the line of the street that divides
        East from West ([lat, lng] points, north to south) and the side to use when nothing
        else tells ("no_direction"). On such streets the table has "E 7TH AVE" and either
        "W 7TH AVE" or the bare "5TH AVE" (the county list writes some west parts that way).

        Google often leaves the E or W out ("152 7th Ave"). The side is then, in order:
          1. the only side where this house number is in the table,
          2. the side of the dividing line the address's map location (lat, lng) is on,
          3. split["no_direction"] (West in Roselle), marked to check.

        Returns None when the street is not split this way, otherwise find()'s answer plus
            street   the street name in the table that matched ("W 7TH AVE")
            how      'given' (the address said E or W), 'number', 'location', 'default'
                     or 'nearest' (the default side has no stretch near the number)
        """
        if not split:
            return None
        words = normalize_street(street).split()
        given = None
        if len(words) >= 3 and words[0] in ('E', 'W'):
            given, words = words[0], words[1:]
        name = ' '.join(words)
        names = {'E': ['E ' + name], 'W': ['W ' + name, name]}
        names = {side: [n for n in found if self._rows(town_id, n, zip_code)] for side, found in names.items()}
        if not (names['E'] and names['W']):
            return None

        def answer(side, how, needs_check=False):
            #The house number itself first, then the nearest stretch of the street
            for look in (lambda n: self._exact(self._rows(town_id, n, zip_code), house_number),
                         lambda n: self.find(town_id, house_number, n, zip_code)):
                for n in names[side]:
                    found = look(n)
                    if found:
                        found.update(street=n, how=how, needs_check=found['needs_check'] or needs_check)
                        return found
            return None

        if given:
            return answer(given, 'given')
        on_sides = [side for side in 'EW' if any(self._exact(self._rows(town_id, n, zip_code), house_number)
                                                  for n in names[side])]
        if len(on_sides) == 1:
            return answer(on_sides[0], 'number')
        if location and split.get('line'):
            side, meters = side_of_line(location[0], location[1], split['line'])
            return answer(side, 'location', meters < split.get('near_line_meters', 0))
        default = split.get('no_direction', 'W')
        #Only when that side has no stretch near this house number
        return answer(default, 'default', True) or answer('E' if default == 'W' else 'W', 'nearest', True)


def side_of_line(lat, lng, line):
    """('E' or 'W', meters away): which side of a line running north to south a point is on.

    line is a list of [lat, lng] points from north to south. Past either end the
    nearest end piece of the line is extended. Good enough within a town.
    """
    scale = math.cos(math.radians(lat))
    for a, b in zip(line, line[1:]):
        if b[0] <= lat <= a[0]:
            break
    else:
        a, b = (line[0], line[1]) if lat > line[0][0] else (line[-2], line[-1])
    t = (lat - a[0]) / (b[0] - a[0]) if b[0] != a[0] else 0
    line_lng = a[1] + (b[1] - a[1]) * t
    return ('E' if lng > line_lng else 'W'), abs(lng - line_lng) * scale * METERS_PER_DEGREE
