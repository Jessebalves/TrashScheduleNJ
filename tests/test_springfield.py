"""Springfield is checked against the Township's 2026 DPW Services Brochure."""
import collections
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
    found = set()
    sunday = pickup_schedule.sunday_of(day(first))
    while sunday <= day(last):
        answer = pickup_schedule.week_schedule(town, zone, sunday)
        stream = [s for s in answer['streams'] if s['id'] == stream_id][0]
        for item in answer['days']:
            date = day(item['date'])
            if item['name'] in stream['pickups'] and day(first) <= date <= day(last):
                found.add(item['date'])
        sunday += datetime.timedelta(days=7)
    return sorted(found)


class SpringfieldSchedule(unittest.TestCase):
    def setUp(self):
        self.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['springfield']

    def test_trash_weekly_and_twice_a_week_in_summer(self):
        #South of Mountain Ave Thursday, north Friday; May 26 - September 4 Mon & Thu / Tue & Fri
        self.assertEqual(pickup_dates(self.town, 'S', 'garbage', '2026-05-17', '2026-05-30'), ['2026-05-21', '2026-05-28'])
        self.assertEqual(pickup_dates(self.town, 'S', 'garbage', '2026-05-31', '2026-06-06'), ['2026-06-01', '2026-06-04'])
        self.assertEqual(pickup_dates(self.town, 'N', 'garbage', '2026-05-24', '2026-05-30'), ['2026-05-26', '2026-05-29'])
        self.assertEqual(pickup_dates(self.town, 'N', 'garbage', '2026-08-30', '2026-09-12'), ['2026-09-01', '2026-09-04', '2026-09-11'])
        self.assertEqual(pickup_dates(self.town, 'S', 'garbage', '2026-08-30', '2026-09-12'), ['2026-08-31', '2026-09-03', '2026-09-10'])

    def test_trash_holidays_move_to_the_next_day(self):
        #Recycle Coach: Thanksgiving trash on the south side is picked up on Friday (the brochure said Saturday)
        self.assertEqual(pickup_dates(self.town, 'S', 'garbage', '2026-01-01', '2026-01-10'), ['2026-01-02', '2026-01-08'])
        self.assertEqual(pickup_dates(self.town, 'S', 'garbage', '2026-11-22', '2026-11-28'), ['2026-11-27'])
        self.assertEqual(pickup_dates(self.town, 'N', 'garbage', '2026-12-20', '2026-12-26'), ['2026-12-26'])
        self.assertEqual(pickup_dates(self.town, 'N', 'garbage', '2026-11-22', '2026-11-28'), ['2026-11-27'])

    def test_recycling_holidays(self):
        #"Thursday's collection" moves to Friday on New Year's Day and Thanksgiving
        self.assertEqual(pickup_dates(self.town, 'S', 'containers', '2026-01-01', '2026-01-03'), ['2026-01-02'])
        self.assertEqual(pickup_dates(self.town, 'S', 'containers', '2026-11-22', '2026-11-28'), ['2026-11-27'])

    def test_bulk_dates(self):
        self.assertEqual(pickup_dates(self.town, 'N', 'bulk', '2026-01-01', '2026-12-31'),
                         ['2026-03-18', '2026-06-10', '2026-09-16', '2026-12-09'])


class SpringfieldAddresses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(TOP, 'data', 'springfield.csv'), newline='', encoding='utf-8') as handle:
            cls.rows = list(csv.DictReader(handle))

    def test_mountain_ave_by_side_of_the_street(self):
        #Even numbers are on the north side of Mountain Ave, odd on the south side
        for row in self.rows:
            if row['Street_Name'] == 'MOUNTAIN AVE':
                self.assertEqual(row['Zone'], 'N' if row['Side'] == 'E' else 'S', row)

    def test_recycle_coach(self):
        #Checked in Springfield's Recycle Coach on 2026-11-21 (trash Friday = N, Thursday = S)
        book = AddressBook()
        for row in self.rows:
            book.add('springfield', row['Street_Name'], row['Low_Range'], row['High_Range'], row['Side'], row['ZIP'],
                     row['Zone'], row['Needs_Check'] == 'Y')
        checked = [(132, 'Baltusrol Way', 'N'), (216, 'Milltown Rd', 'S'), (180, 'S Springfield Ave', 'S'),
                   (330, 'Mountain Ave', 'N'), (345, 'Mountain Ave', 'S'), (270, 'Hillside Ave', 'S'),
                   (307, 'Hillside Ave', 'N'), (190, 'Morris Ave', 'S'), (240, 'Morris Ave', 'N'), (40, 'Linden Ave', 'S'),
                   (236, 'Short Hills Ave', 'N'), (20, 'Meisel Ave', 'S'), (16, 'Caldwell Pl', 'N'),
                   (92, 'Millburn Ave', 'N'), (18, 'Church Mall', 'S'), (20, 'Center St', 'N'), (99, 'Newbrook Ln', 'S')]
        for number, street, zone in checked:
            self.assertEqual(book.find('springfield', number, street, '07081')['zone'], zone, (number, street))

    def test_county_slips_are_fixed(self):
        names = {row['Street_Name'] for row in self.rows}
        for slip in ('REMER AVENUE AVE', 'MEISEL AVENUE AVE', 'A FOREST DR', 'B TROY DR'):
            self.assertNotIn(slip, names)

    def test_both_sides(self):
        self.assertEqual({row['Zone'] for row in self.rows}, {'N', 'S'})


if __name__ == '__main__':
    unittest.main()
