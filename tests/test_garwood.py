"""Garwood is checked against every date of the borough's 2026 DPW Schedule of Services."""
import csv
import datetime
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

import pickup_schedule
from address_lookup import AddressBook

#The calendar's G (garbage) and R (recycling) days, side -> month -> days
GARBAGE = {
    'N': {1: [2, 6, 9, 13, 16, 20, 23, 27, 30], 2: [3, 6, 10, 13, 17, 20, 24, 27], 3: [3, 6, 10, 13, 17, 20, 24, 27, 31],
          4: [7, 10, 14, 17, 21, 24, 28], 5: [1, 5, 8, 12, 15, 19, 22, 26, 29], 6: [2, 5, 9, 12, 16, 23, 26, 30],
          7: [7, 10, 14, 17, 21, 24, 28, 31], 8: [4, 7, 11, 14, 18, 21, 25, 28], 9: [1, 4, 8, 11, 15, 18, 22, 25, 29],
          10: [2, 6, 9, 13, 16, 20, 23, 27, 30], 11: [4, 6, 10, 13, 17, 20, 24], 12: [1, 4, 8, 11, 15, 18, 22, 29]},
    'S': {1: [5, 8, 12, 15, 19, 22, 26, 29], 2: [2, 5, 9, 12, 17, 19, 23, 26], 3: [2, 5, 9, 12, 16, 19, 23, 26, 30],
          4: [2, 6, 9, 13, 16, 20, 23, 27, 30], 5: [4, 7, 11, 14, 18, 21, 28], 6: [1, 4, 8, 11, 15, 18, 22, 25, 29],
          7: [2, 6, 9, 13, 16, 20, 23, 27, 30], 8: [3, 6, 10, 13, 17, 20, 24, 27, 31], 9: [3, 10, 14, 17, 21, 24, 28],
          10: [1, 5, 8, 12, 15, 19, 22, 26, 29], 11: [2, 5, 9, 12, 16, 19, 23, 30], 12: [3, 7, 10, 14, 17, 21, 28]},
}
RECYCLING = {
    'N': {1: [14, 28], 2: [11, 25], 3: [11, 25], 4: [8, 22], 5: [6, 20], 6: [3, 17], 7: [1, 15, 29], 8: [12, 26],
          9: [9, 23], 10: [7, 21], 11: [4, 18], 12: [2, 16, 30]},
    'S': {1: [7, 21], 2: [4, 18], 3: [4, 18], 4: [1, 15, 29], 5: [13, 27], 6: [10, 24], 7: [8, 22], 8: [5, 19],
          9: [2, 16, 30], 10: [14, 28], 11: [11, 25], 12: [9, 23]},
}


def day(text):
    return datetime.date.fromisoformat(text)


def pickup_dates(town, zone, stream_id, first, last):
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


def listed(months):
    return [datetime.date(2026, m, d) for m, days in sorted(months.items()) for d in days]


class GarwoodSchedule(unittest.TestCase):
    def setUp(self):
        self.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['garwood']
        self.year = (day('2026-01-01'), day('2026-12-31'))

    def test_every_garbage_date(self):
        for zone, months in GARBAGE.items():
            self.assertEqual(pickup_dates(self.town, zone, 'garbage', *self.year), listed(months), zone)

    def test_every_recycling_date(self):
        #Veterans Day (Wednesday 11/11) is marked on the calendar, but South Side recycling is collected
        for zone, months in RECYCLING.items():
            self.assertEqual(pickup_dates(self.town, zone, 'containers', *self.year), listed(months), zone)

    def test_holiday_moves(self):
        north = pickup_schedule.week_schedule(self.town, 'N', day('2026-11-03'))
        self.assertIn('Garbage moves from Tuesday to Wednesday because of Election Day.', north['changes'])
        south = pickup_schedule.week_schedule(self.town, 'S', day('2026-02-16'))
        self.assertIn("Garbage moves from Monday to Tuesday because of Presidents' Day.", south['changes'])

    def test_grass_trees_bulk_and_leaves(self):
        grass = pickup_dates(self.town, 'S', 'yard', *self.year)
        self.assertEqual((grass[0], grass[-1], len(grass)), (day('2026-04-01'), day('2026-10-28'), 31))
        self.assertEqual(pickup_dates(self.town, 'N', 'christmas_trees', *self.year),
                         [day('2026-01-07'), day('2026-01-14'), day('2026-01-21'), day('2026-01-28')])
        self.assertEqual(pickup_dates(self.town, 'N', 'bulk', *self.year),
                         [day('2026-04-06'), day('2026-06-15'), day('2026-08-17'), day('2026-10-19')])
        self.assertEqual(pickup_dates(self.town, 'S', 'leaves', *self.year),
                         [day('2026-11-09'), day('2026-11-23'), day('2026-12-07'), day('2026-12-16')])


class GarwoodAddresses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['garwood']
        with open(os.path.join(TOP, 'data', 'garwood.csv'), newline='', encoding='utf-8') as handle:
            cls.rows = list(csv.DictReader(handle))

    def zones_on(self, street):
        return {row['Zone'] for row in self.rows if row['Street_Name'] == street}

    def test_sides_of_the_railroad(self):
        #Numbered avenues are north of the railroad, the tree streets south of it
        for street in ('NORTH AVE', '2ND AVE', '3RD AVE', '4TH AVE', '5TH AVE', 'WINSLOW PL', 'WALNUT ST'):
            self.assertEqual(self.zones_on(street), {'N'}, street)
        for street in ('SPRUCE AVE', 'LOCUST AVE', 'BEECH AVE', 'PINE AVE', 'HAZEL AVE', 'HEMLOCK AVE',
                       'HICKORY AVE', 'EAST ST', 'WEST ST'):
            self.assertEqual(self.zones_on(street), {'S'}, street)

    def test_south_ave(self):
        #South of the railroad, but 432 South Ave is North Side (Recycle Coach), as its election district says
        for row in self.rows:
            if row['Street_Name'] == 'SOUTH AVE':
                self.assertEqual(row['Zone'], 'N' if row['Low_Range'] in ('432', '450') else 'S', row)

    def test_recycle_coach(self):
        #Checked in Garwood's Recycle Coach on 2026-11-21 (garbage Tue/Fri = N, Mon/Thu = S)
        book = AddressBook()
        for row in self.rows:
            book.add('garwood', row['Street_Name'], row['Low_Range'], row['High_Range'], row['Side'], row['ZIP'],
                     row['Zone'], row['Needs_Check'] == 'Y')
        checked = [(306, 'North Ave', 'N'), (217, '3rd Ave', 'N'), (225, 'Spruce Ave', 'S'), (300, 'Hickory Ave', 'S'),
                   (245, 'Willow Ave', 'N'), (210, 'New St', 'N'), (115, 'Myrtle Ave', 'N'), (167, 'Myrtle Ave', 'S'),
                   (201, 'Myrtle Ave', 'S'), (91, 'Center St', 'N'), (432, 'South Ave', 'N'), (213, 'Maple St', 'N'),
                   (214, 'Maple St', 'N'), (117, 'Oak St', 'N'), (416, 'Oak St', 'N'), (419, 'Oak St', 'N'),
                   (405, 'Brookside Pl', 'N'), (5, 'Cedar St', 'N')]
        for number, street, zone in checked:
            self.assertEqual(book.find('garwood', number, street, '07027')['zone'], zone, (number, street))
        #79 Mountain Ave is on the county list but not in Garwood's Recycle Coach
        self.assertFalse(any(row['Street_Name'] == 'MOUNTAIN AVE' for row in self.rows))

    def test_north_side_streets_south_of_the_railroad(self):
        #"North Side includes all of Willow Avenue, New Street, and the dead ends of Myrtle Avenue off of New Street"
        self.assertEqual(self.zones_on('WILLOW AVE'), {'N'})
        self.assertEqual(self.zones_on('NEW ST'), {'N'})
        for row in self.rows:
            if row['Street_Name'] == 'MYRTLE AVE':
                self.assertEqual(row['Zone'], 'N' if int(row['High_Range']) < 164 else 'S', row)

    def test_every_zone_is_in_the_rules_file(self):
        self.assertEqual({row['Zone'] for row in self.rows}, set(self.town['zones']))


if __name__ == '__main__':
    unittest.main()
