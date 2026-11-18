"""The Township of Union is checked against its 2026 Recycling Collection Calendar."""
import csv
import datetime
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

import pickup_schedule
from address_lookup import AddressBook

#Read off the calendar: the blue (commingle) Wednesdays. The red (brown goods)
#Wednesdays are the ones in between.
COMMINGLED = """JAN 7, JAN 21, FEB 4, FEB 18, MAR 4, MAR 18, APR 1, APR 15, APR 29, MAY 13, MAY 27,
JUN 10, JUN 24, JUL 8, JUL 22, AUG 5, AUG 19, SEP 2, SEP 16, SEP 30, OCT 14, OCT 28, NOV 11, NOV 25,
DEC 9, DEC 23"""
SPRING_LEAVES = "MAR 26, MAR 27, APR 2, APR 3"
HOLIDAYS = "JAN 1, MAY 25, SEP 7, NOV 26, DEC 25"

MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']


def dates(text):
    result = []
    for item in text.replace('\n', ' ').split(','):
        month, day = item.split()
        result.append(datetime.date(2026, MONTHS.index(month) + 1, int(day)))
    return result


def pickup_dates(town, zone, stream_id):
    """Every date in 2026 the website would mark for one stream."""
    found = set()
    sunday = datetime.date(2025, 12, 28)
    while sunday.year < 2027:
        answer = pickup_schedule.week_schedule(town, zone, sunday)
        stream = [s for s in answer['streams'] if s['id'] == stream_id][0]
        for day in answer['days']:
            if day['name'] in stream['pickups'] and day['date'].startswith('2026'):
                found.add(datetime.date.fromisoformat(day['date']))
        sunday += datetime.timedelta(days=7)
    return sorted(found)


class UnionSchedule(unittest.TestCase):
    def setUp(self):
        self.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['union']

    def test_holidays(self):
        self.assertEqual(sorted(pickup_schedule.holidays_in_year(self.town, 2026)), dates(HOLIDAYS))

    def test_commingled_and_brown_goods_alternate(self):
        blue = dates(COMMINGLED)
        self.assertEqual(pickup_dates(self.town, 'WEST', 'containers'), blue)
        wednesdays = [datetime.date(2026, 1, 7) + datetime.timedelta(weeks=n) for n in range(52)]
        self.assertEqual(pickup_dates(self.town, 'EAST', 'paper'), [d for d in wednesdays if d not in blue])

    def test_spring_leaves(self):
        spring = dates(SPRING_LEAVES)
        both = sorted(pickup_dates(self.town, 'WEST', 'spring_leaves') + pickup_dates(self.town, 'EAST', 'spring_leaves'))
        self.assertEqual(both, spring)

    def test_grass_runs_april_9_to_october_30(self):
        west = pickup_dates(self.town, 'WEST', 'yard')
        east = pickup_dates(self.town, 'EAST', 'yard')
        self.assertEqual((west[0], west[-1]), (datetime.date(2026, 4, 9), datetime.date(2026, 10, 29)))
        self.assertEqual((east[0], east[-1]), (datetime.date(2026, 4, 10), datetime.date(2026, 10, 30)))
        self.assertEqual({d.weekday() for d in west}, {3})
        self.assertEqual({d.weekday() for d in east}, {4})

    def test_leaves_and_the_thanksgiving_make_up(self):
        west = pickup_dates(self.town, 'WEST', 'leaves')
        east = pickup_dates(self.town, 'EAST', 'leaves')
        self.assertEqual(west[0], datetime.date(2026, 10, 1))
        self.assertNotIn(datetime.date(2026, 11, 26), west)
        self.assertIn(datetime.date(2026, 11, 28), west)          #West Zone make-up, Saturday
        self.assertNotIn(datetime.date(2026, 12, 25), east)       #Christmas
        self.assertIn(datetime.date(2026, 12, 31), west)

    def test_trash_and_bulk_skip_holidays(self):
        self.assertNotIn(datetime.date(2026, 5, 25), pickup_dates(self.town, 'WEST', 'bulk'))
        self.assertNotIn(datetime.date(2026, 9, 7), pickup_dates(self.town, 'WEST', 'garbage'))
        self.assertIn(datetime.date(2026, 9, 8), pickup_dates(self.town, 'EAST', 'bulk'))
        self.assertNotIn(datetime.date(2026, 1, 1), pickup_dates(self.town, 'WEST', 'garbage'))


class UnionAddresses(unittest.TestCase):
    def setUp(self):
        self.book = AddressBook()
        with open(os.path.join(TOP, 'data', 'union.csv'), newline='', encoding='utf-8') as handle:
            for row in csv.DictReader(handle):
                self.book.add('union', row['Street_Name'], row['Low_Range'], row['High_Range'],
                              row['Side'], row['ZIP'], row['Zone'], row['Needs_Check'])

    def first_number(self, street):
        with open(os.path.join(TOP, 'data', 'union.csv'), newline='', encoding='utf-8') as handle:
            return next(int(r['Low_Range']) for r in csv.DictReader(handle) if r['Street_Name'] == street)

    def test_streets_from_the_route_list(self):
        #Collection Routes 2015: bulk Monday = West, bulk Tuesday = East
        for street, zone in (('ACADEMY RD', 'WEST'), ('ADAMS AVE', 'EAST'), ('STUYVESANT AVE', 'EAST'),
                             ('MORRIS AVE', 'EAST'), ('BURNET AVE', 'WEST'), ('GALLOPING HILL RD', 'EAST')):
            found = self.book.find('union', self.first_number(street), street)
            self.assertEqual(found['zone'], zone, street)
            self.assertFalse(found['needs_check'], street)

    def test_spellings(self):
        self.assertEqual(self.book.find('union', self.first_number('ACADEMY RD'), 'Academy Road')['zone'], 'WEST')
        self.assertIsNotNone(self.book.find('union', self.first_number('REID ST'), 'Reid Street'))

    def test_unsure_streets_are_marked_to_check(self):
        #Listed East, but every street around it is West
        self.assertTrue(self.book.find('union', self.first_number('HICKORY RD'), 'Hickory Rd')['needs_check'])
        #Not on the 2015 list, zone from the streets around it
        self.assertTrue(self.book.find('union', self.first_number('FIRETHORN DR'), 'Firethorn Dr')['needs_check'])


if __name__ == '__main__':
    unittest.main()
