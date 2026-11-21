"""Mountainside is checked against the borough's 2026 recycling dates."""
import csv
import datetime
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

import pickup_schedule

#"2026 RECYCLING DATES", all Wednesdays (the list runs into January 2027)
RECYCLING = {(2026, 1): [14, 28], (2026, 2): [11, 25], (2026, 3): [11, 25], (2026, 4): [8, 22], (2026, 5): [6, 20],
             (2026, 6): [3, 17], (2026, 7): [1, 15, 29], (2026, 8): [12, 26], (2026, 9): [9, 23], (2026, 10): [7, 21],
             (2026, 11): [4, 18], (2026, 12): [2, 16, 30], (2027, 1): [13, 27]}


def pickup_dates(town, first, last):
    found = set()
    sunday = pickup_schedule.sunday_of(first)
    while sunday <= last:
        answer = pickup_schedule.week_schedule(town, 'ALL', sunday)
        for item in answer['days']:
            date = datetime.date.fromisoformat(item['date'])
            if item['name'] in answer['streams'][0]['pickups'] and first <= date <= last:
                found.add(date)
        sunday += datetime.timedelta(days=7)
    return sorted(found)


class Mountainside(unittest.TestCase):
    def setUp(self):
        self.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['mountainside']

    def test_every_recycling_date(self):
        expected = [datetime.date(y, m, d) for (y, m), days in sorted(RECYCLING.items()) for d in days]
        self.assertEqual(pickup_dates(self.town, datetime.date(2026, 1, 1), datetime.date(2027, 1, 31)), expected)

    def test_recycling_is_the_only_pickup(self):
        self.assertEqual([s['id'] for s in self.town['streams']], ['containers'])
        self.assertIn('does not pick up household trash', self.town['important_notes'][0])

    def test_recycling_contract_reminder(self):
        #The recycling contract runs to January 2028: from September 1, 2027 the maintainers are reminded
        towns = {'mountainside': self.town}
        self.assertEqual(pickup_schedule.due_reminders(towns, datetime.date(2027, 8, 31)), [])
        due = pickup_schedule.due_reminders(towns, datetime.date(2027, 9, 1))
        self.assertEqual(len(due), 1)
        self.assertIn('January 2028', due[0][1])

    def test_one_zone(self):
        with open(os.path.join(TOP, 'data', 'mountainside.csv'), newline='', encoding='utf-8') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual({row['Zone'] for row in rows}, {'ALL'})
        self.assertFalse(any(row['Street_Name'][0].isdigit() for row in rows))


if __name__ == '__main__':
    unittest.main()
