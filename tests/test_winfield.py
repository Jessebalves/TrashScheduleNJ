"""Winfield: garbage Tuesday and Friday, recycling every other Friday, bulky waste the last Wednesday."""
import csv
import datetime
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

import pickup_schedule


def day(text):
    return datetime.date.fromisoformat(text)


def pickup_dates(town, stream_id, first, last):
    found = set()
    sunday = pickup_schedule.sunday_of(first)
    while sunday <= last:
        answer = pickup_schedule.week_schedule(town, 'ALL', sunday)
        stream = [s for s in answer['streams'] if s['id'] == stream_id][0]
        for item in answer['days']:
            date = day(item['date'])
            if item['name'] in stream['pickups'] and first <= date <= last:
                found.add(date)
        sunday += datetime.timedelta(days=7)
    return sorted(found)


class WinfieldSchedule(unittest.TestCase):
    def setUp(self):
        self.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['winfield']

    def test_garbage_twice_a_week(self):
        week = (day('2026-11-15'), day('2026-11-21'))
        self.assertEqual(pickup_dates(self.town, 'garbage', *week), [day('2026-11-17'), day('2026-11-20')])

    def test_recycling_continues_giordanos_2025_fridays(self):
        #2025: every other Friday, the last ones December 12 and 26
        recycling = pickup_dates(self.town, 'containers', day('2026-01-01'), day('2026-03-31'))
        self.assertEqual(recycling, [day('2026-01-09'), day('2026-01-23'), day('2026-02-06'), day('2026-02-20'),
                                     day('2026-03-06'), day('2026-03-20')])
        self.assertEqual(day('2026-01-09') - day('2025-12-26'), datetime.timedelta(days=14))

    def test_bulky_waste_last_wednesday(self):
        self.assertEqual(pickup_dates(self.town, 'bulk', day('2026-09-01'), day('2026-12-31')),
                         [day('2026-09-30'), day('2026-10-28'), day('2026-11-25'), day('2026-12-30')])

    def test_one_zone(self):
        with open(os.path.join(TOP, 'data', 'winfield.csv'), newline='', encoding='utf-8') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual({row['Zone'] for row in rows}, {'ALL'})
        self.assertEqual(len(rows), 10)


if __name__ == '__main__':
    unittest.main()
