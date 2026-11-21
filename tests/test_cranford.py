"""Cranford is checked against every date of the township's 2026 Curbside Recycling Calendar."""
import csv
import datetime
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

import pickup_schedule
from address_lookup import AddressBook

#The 2026 calendar (updated 12-10-2025), month by month: the Monday and Tuesday pickups of
#the North Side and of the South Side. Memorial Day moved North Side Monday to Friday 5/29,
#Labor Day moved South Side Monday to Friday 9/11. February 23-24 (South Side) was moved to
#February 27-28 by the township's storm notice of 2/22/2026.
NORTH_MONDAYS = ['01-05', '01-19', '02-02', '02-16', '03-02', '03-16', '03-30', '04-13', '04-27', '05-11', '05-29',
                 '06-08', '06-22', '07-06', '07-20', '08-03', '08-17', '08-31', '09-14', '09-28', '10-12', '10-26',
                 '11-09', '11-23', '12-07', '12-21']
NORTH_TUESDAYS = ['01-06', '01-20', '02-03', '02-17', '03-03', '03-17', '03-31', '04-14', '04-28', '05-12', '05-26',
                  '06-09', '06-23', '07-07', '07-21', '08-04', '08-18', '09-01', '09-15', '09-29', '10-13', '10-27',
                  '11-10', '11-24', '12-08', '12-22']
SOUTH_MONDAYS = ['01-12', '01-26', '02-09', '02-27', '03-09', '03-23', '04-06', '04-20', '05-04', '05-18', '06-01',
                 '06-15', '06-29', '07-13', '07-27', '08-10', '08-24', '09-11', '09-21', '10-05', '10-19', '11-02',
                 '11-16', '11-30', '12-14', '12-28']
SOUTH_TUESDAYS = ['01-13', '01-27', '02-10', '02-28', '03-10', '03-24', '04-07', '04-21', '05-05', '05-19', '06-02',
                  '06-16', '06-30', '07-14', '07-28', '08-11', '08-25', '09-08', '09-22', '10-06', '10-20', '11-03',
                  '11-17', '12-01', '12-15', '12-29']


def pickup_dates(town, zone, first, last):
    """Every recycling date from first to last the website would mark."""
    found = set()
    sunday = pickup_schedule.sunday_of(first)
    while sunday <= last:
        answer = pickup_schedule.week_schedule(town, zone, sunday)
        stream = answer['streams'][0]
        for item in answer['days']:
            date = datetime.date.fromisoformat(item['date'])
            if item['name'] in stream['pickups'] and first <= date <= last:
                found.add(date)
        sunday += datetime.timedelta(days=7)
    return sorted(found)


class CranfordSchedule(unittest.TestCase):
    def setUp(self):
        self.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['cranford']

    def test_recycling_is_the_only_pickup(self):
        self.assertEqual([s['id'] for s in self.town['streams']], ['containers'])
        self.assertIn('does not pick up household trash', self.town['important_notes'][0])

    def test_every_2026_date(self):
        year = (datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
        for zone, dates in (('NM', NORTH_MONDAYS), ('NT', NORTH_TUESDAYS), ('SM', SOUTH_MONDAYS), ('ST', SOUTH_TUESDAYS)):
            self.assertEqual(pickup_dates(self.town, zone, *year),
                             [datetime.date.fromisoformat('2026-' + d) for d in dates], zone)

    def test_holiday_move_is_shown(self):
        answer = pickup_schedule.week_schedule(self.town, 'SM', datetime.date(2026, 9, 7))
        self.assertEqual(answer['streams'][0]['pickups'], ['Friday'])
        self.assertIn('Labor Day', ' '.join(answer['changes']))


class CranfordAddresses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['cranford']
        cls.book = AddressBook()
        with open(os.path.join(TOP, 'data', 'cranford.csv'), newline='', encoding='utf-8') as handle:
            for row in csv.DictReader(handle):
                cls.book.add('cranford', row['Street_Name'], row['Low_Range'], row['High_Range'],
                             row['Side'], row['ZIP'], row['Zone'], row['Needs_Check'] == 'Y')

    def zone(self, number, street):
        street = self.town['street_names'].get(street.upper(), street)
        found = self.book.find('cranford', number, street, '07016')
        return found and (found['zone'], found['needs_check'])

    def test_whole_streets(self):
        self.assertEqual(self.zone(10, 'Alden St'), ('NM', False))
        self.assertEqual(self.zone(20, 'Albany Ave'), ('NT', False))
        self.assertEqual(self.zone(15, 'Burnside Ave'), ('SM', False))
        self.assertEqual(self.zone(20, 'Hollywood Ave'), ('ST', False))

    def test_split_streets(self):
        #Casino Ave: Linden Pl to Riverside Dr is Tuesday, Linden Pl to Pacific Ave Monday
        self.assertEqual(self.zone(318, 'Casino Ave')[0], 'NT')
        self.assertEqual(self.zone(450, 'Casino Ave')[0], 'NM')
        #Springfield Ave: the west side (odd numbers) Monday, the east side (even) Tuesday
        self.assertEqual(self.zone(1131, 'Springfield Ave')[0], 'NM')
        self.assertEqual(self.zone(704, 'Springfield Ave')[0], 'NT')
        #S Union Ave: South Ave to Lincoln Ave is South Tuesday, past Lincoln Ave South Monday
        self.assertEqual(self.zone(40, 'S Union Ave')[0], 'ST')
        self.assertEqual(self.zone(310, 'S Union Ave')[0], 'SM')

    def test_names_with_a_direction_at_the_end(self):
        self.assertEqual(self.zone(100, 'South Avenue West')[0], 'ST')
        self.assertEqual(self.zone(100, 'Lincoln Ave E')[0], 'ST')
        self.assertEqual(self.zone(20, 'North Ave W')[0], 'NM')

    def test_every_zone_is_in_the_rules_file(self):
        zones = {row[4] for rows in self.book.streets.values() for row in rows}
        self.assertEqual(zones, set(self.town['zones']))


if __name__ == '__main__':
    unittest.main()
