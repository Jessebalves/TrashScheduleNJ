"""The "next pickups" list used by the new website design (pickup_schedule.upcoming)."""
import datetime
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)
os.environ['ADDRESS_SOURCE'] = 'csv'

import pickup_schedule as schedule
import test_server

test_server.load_everything()
TOWNS = schedule.load_towns(os.path.join(TOP, 'towns'))
day = datetime.date.fromisoformat


class Upcoming(unittest.TestCase):
    def test_thanksgiving_moves_elizabeth_garbage_to_friday(self):
        #Ward 1 is picked up Monday and Thursday, Elizabeth moves holiday pickups a day
        result = schedule.upcoming(TOWNS['elizabeth'], '1', day('2026-11-24'), 3)
        dates = [p['date'] for p in result['pickups']]
        self.assertEqual(dates, ['2026-11-25', '2026-11-27', '2026-11-30'])
        friday = result['pickups'][1]
        self.assertEqual(friday['streams'], [{'id': 'garbage', 'label': 'Garbage', 'moved': True}])
        self.assertEqual(result['notices'], [{
            'date': '2026-11-26', 'new_date': '2026-11-27', 'holiday': 'Thanksgiving',
            'message': 'Garbage moves from Thursday, Nov 26 to Friday, Nov 27 because of Thanksgiving.'}])

    def test_kenilworth_skips_the_holiday(self):
        #The Monday & Thursday route has no pickup on Thanksgiving. The town-wide paper
        #pickup on Tuesday Dec 1 is the second one
        result = schedule.upcoming(TOWNS['kenilworth'], 'MON_THU', day('2026-11-25'), 2)
        self.assertEqual([p['date'] for p in result['pickups']], ['2026-11-30', '2026-12-01'])
        self.assertEqual(len(result['notices']), 1)
        self.assertIsNone(result['notices'][0]['new_date'])
        self.assertIn('No garbage pickup on Thursday, Nov 26', result['notices'][0]['message'])

    def test_today_counts_and_past_changes_are_left_out(self):
        result = schedule.upcoming(TOWNS['kenilworth'], 'TUE_FRI', day('2026-11-04'), 1)
        self.assertEqual(result['pickups'][0]['date'], '2026-11-04')
        self.assertTrue(result['pickups'][0]['streams'][0]['moved'])
        later = schedule.upcoming(TOWNS['kenilworth'], 'TUE_FRI', day('2026-11-05'), 4)
        self.assertEqual(later['notices'], [])

    def test_streams_on_one_day_keep_the_town_file_order(self):
        result = schedule.upcoming(TOWNS['kenilworth'], 'TUE_FRI', day('2026-12-01'), 1)
        self.assertEqual([s['id'] for s in result['pickups'][0]['streams']], ['garbage', 'paper'])

    def test_the_week_table_is_unchanged(self):
        week = schedule.week_schedule(TOWNS['elizabeth'], '1', day('2026-11-24'))
        self.assertEqual(week['streams'][2]['pickups'], ['Monday', 'Friday'])
        self.assertEqual(week['changes'], ['Garbage moves from Thursday to Friday because of Thanksgiving.'])


class WebsiteUpcoming(unittest.TestCase):
    def setUp(self):
        self.client = test_server.app.test_client()

    def test_data_answer_has_the_next_pickups(self):
        response = self.client.post('/data', json={'house_number': '20', 'street': 'Atlantic St',
                                                   'town': 'Elizabeth', 'date': '2026-11-24', 'week': 1})
        answer = response.get_json()
        self.assertEqual(response.status_code, 200)
        #Next week is shown in the table, the list still starts today
        self.assertEqual(answer['days'][0]['date'], '2026-11-29')
        self.assertEqual(answer['upcoming']['pickups'][0]['date'], '2026-11-25')
        self.assertEqual(len(answer['upcoming']['pickups']), 4)

    def test_answer_has_the_zip_code_even_when_it_was_left_out(self):
        answer = self.client.post('/data', json={'house_number': '350', 'street': 'Coolidge Dr',
                                                 'town': 'Kenilworth'}).get_json()
        self.assertEqual(answer['address'], {'zip': '07033', 'state': 'NJ'})
        answer = self.client.post('/data', json={'house_number': '142', 'street': 'Elm St',
                                                 'town': 'Elizabeth'}).get_json()
        self.assertEqual(answer['address'], {'zip': '07208', 'state': 'NJ'})

    def test_upcoming_count(self):
        address = {'house_number': '20', 'street': 'Atlantic St', 'town': 'Elizabeth', 'date': '2026-11-24'}
        answer = self.client.post('/data', json=dict(address, upcoming=30)).get_json()
        self.assertEqual(len(answer['upcoming']['pickups']), 30)
        for bad in (0, 61, 'ten', True, 2.5):
            response = self.client.post('/data', json=dict(address, upcoming=bad))
            self.assertEqual(response.status_code, 400, bad)

    def test_new_design_is_the_home_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-page="home"', response.data)
        response.close()
        for page in ('calendar.html', 'which-bin.html', 'settings.html', 'app.js', 'app.css',
                     'data/counties/union.json', 'data/which-bin/union.json',
                     'data/counties/monmouth.json', 'data/which-bin/monmouth.json'):
            response = self.client.get('/' + page)
            self.assertEqual(response.status_code, 200, page)
            response.close()

    def test_old_new_design_links_redirect_to_the_root(self):
        for old, new in (('/new/', '/'), ('/new/index.html', '/'), ('/new/calendar.html', '/calendar.html'),
                         ('/new/settings.html', '/settings.html')):
            response = self.client.get(old)
            self.assertEqual((response.status_code, response.headers['Location']), (301, new), old)

    def test_classic_pages_are_under_classic(self):
        for path, text in (('/classic/', b'Check Trash'), ('/classic/about.html', b'About'),
                           ('/classic/contact.html', b'Contact'), ('/classic/index.js', b'/data'),
                           ('/classic/style.css', b'#trash_table')):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn(text, response.data, path)
            response.close()


if __name__ == '__main__':
    unittest.main()
