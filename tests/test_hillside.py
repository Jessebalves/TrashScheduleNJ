"""Hillside is checked against the township's 2026-2027 Solid Waste/Recycling Collection Schedule."""
import csv
import datetime
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

import pickup_schedule
from address_lookup import AddressBook

#Read off the calendar: the green (newspaper/cardboard) Wednesdays of 2026.
#The pink (commingled) Wednesdays are the ones in between.
PAPER_2026 = """JAN 7, JAN 21, FEB 4, FEB 18, MAR 4, MAR 18, APR 1, APR 15, APR 29, MAY 13, MAY 27,
JUN 10, JUN 24, JUL 8, JUL 22, AUG 5, AUG 19, SEP 2, SEP 16, SEP 30, OCT 14, OCT 28, NOV 11, NOV 25,
DEC 9, DEC 23"""
#The black "H" days, 2026 and 2027
HOLIDAYS = ['2026-01-01', '2026-05-25', '2026-09-07', '2026-11-26', '2026-12-25',
            '2027-01-01', '2027-05-31', '2027-09-06', '2027-11-25', '2027-12-24']

MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']


def dates(text, year):
    result = []
    for item in text.replace('\n', ' ').split(','):
        month, day = item.split()
        result.append(datetime.date(year, MONTHS.index(month) + 1, int(day)))
    return result


def pickup_dates(town, zone, stream_id, year):
    """Every date in a year the website would mark for one stream."""
    found = set()
    sunday = pickup_schedule.sunday_of(datetime.date(year, 1, 1))
    while sunday.year <= year:
        answer = pickup_schedule.week_schedule(town, zone, sunday)
        stream = [s for s in answer['streams'] if s['id'] == stream_id][0]
        for day in answer['days']:
            if day['name'] in stream['pickups'] and day['date'].startswith(str(year)):
                found.add(datetime.date.fromisoformat(day['date']))
        sunday += datetime.timedelta(days=7)
    return sorted(found)


class HillsideSchedule(unittest.TestCase):
    def setUp(self):
        self.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['hillside']

    def test_holidays(self):
        for year in (2026, 2027):
            found = sorted(d.isoformat() for d in pickup_schedule.holidays_in_year(self.town, year)
                           if d.weekday() < 5)    #Christmas 2027 is a Saturday, not on the calendar
            self.assertEqual(found, [h for h in HOLIDAYS if h.startswith(str(year))])

    def test_paper_and_commingled_alternate(self):
        paper = dates(PAPER_2026, 2026)
        self.assertEqual(pickup_dates(self.town, '1', 'paper', 2026), paper)
        wednesdays = [d for d in (datetime.date(2026, 1, 1) + datetime.timedelta(days=n) for n in range(365))
                      if d.weekday() == 2]
        self.assertEqual(pickup_dates(self.town, '2', 'containers', 2026), [d for d in wednesdays if d not in paper])

    def test_the_pattern_carries_into_2027(self):
        #Green on Jan 6, Jun 9 and Dec 22, 2027, pink on Dec 29, 2027
        paper = pickup_dates(self.town, '1', 'paper', 2027)
        for day in ('2027-01-06', '2027-06-09', '2027-12-22'):
            self.assertIn(datetime.date.fromisoformat(day), paper)
        self.assertIn(datetime.date(2027, 12, 29), pickup_dates(self.town, '1', 'containers', 2027))

    def test_trash_days_skip_holidays(self):
        district_1 = pickup_dates(self.town, '1', 'garbage', 2026)
        district_2 = pickup_dates(self.town, '2', 'garbage', 2026)
        self.assertIn(datetime.date(2026, 11, 23), district_1)
        self.assertNotIn(datetime.date(2026, 11, 26), district_1)   #Thanksgiving
        self.assertIn(datetime.date(2026, 11, 27), district_2)
        self.assertNotIn(datetime.date(2026, 12, 25), district_2)   #Christmas
        self.assertIn(datetime.date(2026, 12, 24), district_1)      #Christmas Eve is a pickup in 2026
        self.assertNotIn(datetime.date(2027, 12, 24), pickup_dates(self.town, '2', 'garbage', 2027))

    def test_bulk_is_the_second_trash_day(self):
        self.assertEqual({d.weekday() for d in pickup_dates(self.town, '1', 'bulk', 2026)}, {3})   #Thursday
        self.assertEqual({d.weekday() for d in pickup_dates(self.town, '2', 'bulk', 2026)}, {4})   #Friday


class HillsideAddresses(unittest.TestCase):
    def setUp(self):
        self.book = AddressBook()
        with open(os.path.join(TOP, 'data', 'hillside.csv'), newline='', encoding='utf-8') as handle:
            for row in csv.DictReader(handle):
                self.book.add('hillside', row['Street_Name'], row['Low_Range'], row['High_Range'],
                              row['Side'], row['ZIP'], row['Zone'], row['Needs_Check'])

    def zone(self, number, street):
        found = self.book.find('hillside', number, street, '07205')
        return found and found['zone']

    def test_streets_from_each_list(self):
        self.assertEqual(self.zone(40, 'Hollywood Ave'), '1')
        self.assertEqual(self.zone(1240, 'St Louis Ave'), '1')
        self.assertEqual(self.zone(520, 'Buchanan Street'), '2')
        self.assertEqual(self.zone(1130, 'Summit Ave'), '2')
        self.assertEqual(self.zone(550, 'Arnold St'), '2')    #not in the county list, added from the Census

    def test_split_streets(self):
        self.assertEqual(self.zone(278, 'Bloy St'), '1')     #Gurd Ave to Liberty Ave
        self.assertEqual(self.zone(344, 'Bloy St'), '2')     #Liberty Ave to Ramsey Ave
        self.assertEqual(self.zone(1301, 'Liberty Ave'), '1')
        self.assertEqual(self.zone(1381, 'Liberty Ave'), '2')
        self.assertEqual(self.zone(246, 'Long Ave'), '1')
        self.assertEqual(self.zone(332, 'Long Ave'), '2')
        self.assertEqual(self.zone(1122, 'North Broad Street'), '1')
        self.assertEqual(self.zone(1528, 'N Broad St'), '2')

    def test_unsure_streets_are_marked_to_check(self):
        self.assertTrue(self.book.find('hillside', 520, 'Buchanan St')['needs_check'])
        self.assertTrue(self.book.find('hillside', 1416, 'N Broad St')['needs_check'])
        self.assertFalse(self.book.find('hillside', 40, 'Hollywood Ave')['needs_check'])


if __name__ == '__main__':
    unittest.main()
