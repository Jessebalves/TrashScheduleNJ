"""Aberdeen is checked against the township's 2026 Community Calendar and Recycle Coach lookups."""
import csv
import datetime
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

import pickup_schedule
from address_lookup import AddressBook


def day(text):
    return datetime.date.fromisoformat(text)


def pickup_dates(town, zone, stream_id, first, last):
    """Every date from first to last the website would mark for one stream."""
    found = set()
    sunday = pickup_schedule.sunday_of(first)
    while sunday <= last:
        answer = pickup_schedule.week_schedule(town, zone, sunday)
        stream = [s for s in answer['streams'] if s['id'] == stream_id][0]
        for item in answer['days']:
            date = day(item['date'])
            if item['name'] in stream['pickups'] and first <= date <= last:
                found.add(date)
        sunday += datetime.timedelta(days=7)
    return sorted(found)


class AberdeenSchedule(unittest.TestCase):
    def setUp(self):
        self.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['aberdeen']

    def test_recycling_alternates_between_the_sections(self):
        #Read off the calendar: the Wednesdays marked "Recycling Section I" / "Section II"
        july = (day('2026-07-01'), day('2026-07-31'))
        self.assertEqual(pickup_dates(self.town, '1', 'containers', *july), [day('2026-07-08'), day('2026-07-22')])
        self.assertEqual(pickup_dates(self.town, '2', 'containers', *july),
                         [day('2026-07-01'), day('2026-07-15'), day('2026-07-29')])
        december = (day('2026-12-01'), day('2026-12-31'))
        self.assertEqual(pickup_dates(self.town, '1', 'containers', *december), [day('2026-12-09'), day('2026-12-23')])
        self.assertEqual(pickup_dates(self.town, '2', 'containers', *december),
                         [day('2026-12-02'), day('2026-12-16'), day('2026-12-30')])
        self.assertIn(day('2026-01-07'), pickup_dates(self.town, '1', 'containers', day('2026-01-01'), day('2026-01-31')))

    def test_garbage_and_bulk(self):
        week = (day('2026-11-15'), day('2026-11-21'))
        self.assertEqual(pickup_dates(self.town, '1', 'garbage', *week), [day('2026-11-16'), day('2026-11-19')])
        self.assertEqual(pickup_dates(self.town, '2', 'garbage', *week), [day('2026-11-17'), day('2026-11-20')])
        self.assertEqual(pickup_dates(self.town, '1', 'bulk', *week), [day('2026-11-19')])
        self.assertEqual(pickup_dates(self.town, '2', 'bulk', *week), [day('2026-11-20')])

    def test_only_three_holidays_and_they_skip(self):
        #"No garbage collection" on Thanksgiving and Christmas; Veterans Day recycling still runs
        self.assertNotIn(day('2026-11-26'), pickup_dates(self.town, '1', 'garbage', day('2026-11-22'), day('2026-11-28')))
        self.assertIn(day('2026-11-27'), pickup_dates(self.town, '2', 'bulk', day('2026-11-22'), day('2026-11-28')))
        self.assertNotIn(day('2026-12-25'), pickup_dates(self.town, '2', 'garbage', day('2026-12-20'), day('2026-12-26')))
        self.assertIn(day('2026-11-11'), pickup_dates(self.town, '1', 'containers', day('2026-11-08'), day('2026-11-14')))


class AberdeenAddresses(unittest.TestCase):
    def setUp(self):
        self.book = AddressBook()
        with open(os.path.join(TOP, 'data', 'aberdeen.csv'), newline='', encoding='utf-8') as handle:
            for row in csv.DictReader(handle):
                self.book.add('aberdeen', row['Street_Name'], row['Low_Range'], row['High_Range'],
                              row['Side'], row['ZIP'], row['Zone'], row['Needs_Check'] == 'Y')

    def section(self, number, street, zip_code=''):
        found = self.book.find('aberdeen', number, street, zip_code)
        return found and found['zone']

    def test_addresses_checked_in_recycle_coach(self):
        for number, street in ((216, 'Wilson Ave'), (148, 'Euclid Ave'), (248, 'Springlawn Ave'),
                               (348, 'Monastery Ln'), (53, 'Harrison Ave'), (18, 'Gerard Ave'),
                               (2, 'Belaire Dr'), (404, 'Cliffwood Ave')):
            self.assertEqual(self.section(number, street), '1', street)
        for number, street in ((50, '1st St'), (50, 'Water St'), (25, 'Lake Blvd'), (35, 'Lenny Ct'),
                               (25, 'White Oak Ln'), (153, 'Van Brackle Rd'), (50, 'Inverness Ct'),
                               (50, 'Heather Glen Dr'), (203, 'Church St')):
            self.assertEqual(self.section(number, street), '2', street)

    def test_any_postal_zip_finds_the_address(self):
        #Aberdeen mail goes to Matawan 07747, Keyport 07735 and Cliffwood 07721
        self.assertEqual(self.section(404, 'Cliffwood Ave', '07735'), '1')
        self.assertEqual(self.section(404, 'Cliffwood Ave', '07721'), '1')

    def test_streets_recycle_coach_does_not_know_are_left_out(self):
        for street in ('Aberdeen Rd', 'Matawan Ter', 'Fawn Dr', 'Greenwood Rd'):
            self.assertIsNone(self.book.find('aberdeen', 50, street), street)


if __name__ == '__main__':
    unittest.main()
