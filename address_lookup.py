"""Finds the pickup zone for a street address.

The address table has one row per stretch of a street:

    town, street name, lowest house number, highest house number,
    side (E = even numbers, O = odd numbers, B = both), ZIP code, zone

A zone is whatever the town uses to decide pickup days. In Elizabeth it is the
ward (1 to 6), in Kenilworth it is the garbage route (MON_THU, TUE_FRI, WED_SAT).

Nothing in this file talks to MySQL or to Flask, so it can be tested on its own.
"""

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
    words[-1] = STREET_TYPES.get(words[-1], words[-1])
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
        rows = self.streets.get((town_id, normalize_street(street)))
        if not rows:
            return None

        zip_code = normalize_zip(zip_code)
        if zip_code:
            #A ZIP code that was given has to match. Rows without one match any.
            rows = [row for row in rows if not row[3] or row[3] == zip_code]
            if not rows:
                return None

        side = 'E' if house_number % 2 == 0 else 'O'
        for low, high, row_side, row_zip, zone, needs_check in rows:
            if low <= house_number <= high and row_side in (side, 'B'):
                return {'zone': zone, 'needs_check': needs_check, 'zip': row_zip}

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
