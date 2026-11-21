#imports
import csv
import datetime
import os
from zoneinfo import ZoneInfo
#used to send recieve requests and send back data
from flask import Flask, request, jsonify, redirect # type: ignore
from flask_cors import CORS # type: ignore
from waitress import serve #type: ignore

#Our own files: finding the zone for an address, and working out the week
from address_lookup import AddressBook, normalize_street, normalize_zip
import pickup_schedule as schedule

HERE = os.path.dirname(os.path.abspath(__file__))

#Filled in when the server starts
towns = {}                  #town id -> the contents of towns/<town>.json
addresses = AddressBook()   #every row of the address table

#Pickup days are worked out for the date in New Jersey, not on the server's clock
NEW_JERSEY = ZoneInfo('America/New_York')


def load_towns():
    """Read the rules for every town from the towns/ folder."""
    towns.clear()
    towns.update(schedule.load_towns(os.path.join(HERE, 'towns')))
    print("Towns loaded:", ', '.join(town['name'] for town in towns.values()))


def add_row(municipality, street, low, high, side, zip_code, zone, needs_check):
    """Put one row of the address table into memory, under the town it belongs to."""
    town = schedule.find_town(towns, municipality)
    if town is None:
        return
    addresses.add(town['id'], street, low, high, side, zip_code, zone, str(needs_check or '').strip() != '')


def load_addresses_from_mysql():
    """Read the whole address table into memory. Restart the service after changing the table."""
    #Connects test_server.py to the MySQL database
    import mysql.connector # type: ignore
    #Database credentials come from environment variables so that no password
    #is stored in this file or in GitHub. In production install.sh writes them to
    #/etc/trashschedulenj/trashschedule.env and the python_server systemd service
    #loads that file.
    dataBase = mysql.connector.connect(
        host = os.environ.get('DB_HOST', 'localhost'),
        user = os.environ.get('DB_USER', 'trashschedule'),
        password = os.environ['DB_PASSWORD'],
        database = os.environ.get('DB_NAME', 'trashschedule')
        )
    cursor = dataBase.cursor()
    print("Connection to MYSQL database running on", os.environ.get('DB_HOST', 'localhost'))
    cursor.execute("SELECT Municipality, Street_Name, Low_Range, High_Range, Side, ZIP, Zone, Needs_Check FROM addresses")
    for row in cursor.fetchall():
        add_row(*row)
    cursor.close()
    dataBase.close()


def load_addresses_from_csv():
    """Read the address table straight from the data/ folder, no database needed.

    For development and for the tests:   ADDRESS_SOURCE=csv python3 test_server.py
    """
    folder = os.path.join(HERE, 'data')
    for file_name in sorted(os.listdir(folder)):
        if not file_name.endswith('.csv'):
            continue
        with open(os.path.join(folder, file_name), newline='', encoding='utf-8') as handle:
            for row in csv.DictReader(handle):
                add_row(row['Municipality'], row['Street_Name'], row['Low_Range'], row['High_Range'],
                        row['Side'], row['ZIP'], row['Zone'], row['Needs_Check'])


def load_everything():
    load_towns()
    if os.environ.get('ADDRESS_SOURCE') == 'csv':
        load_addresses_from_csv()
    else:
        load_addresses_from_mysql()
    print("Address rows loaded:", addresses.row_count)
    #A town whose rules are written but whose addresses are not in yet (Linden, Nov 2026)
    #is not offered: every lookup there would fail
    with_addresses = {town_id for town_id, street in addresses.streets}
    for town_id in [t for t in towns if t not in with_addresses]:
        print("Not offered yet, no addresses:", towns.pop(town_id)['name'])


def problem(message, status=400):
    """Answer with an error status and a message the front end shows to the visitor."""
    return jsonify({'error': message}), status


def town_names():
    return ', '.join(sorted(town['name'] for town in towns.values()))


#Flask
#On the live server nginx hands out the web pages and only passes /data and
#/config on to this program. Serving the pages from here as well means the whole
#website also works on your own computer, at http://127.0.0.1:5000
app = Flask(__name__, static_folder=os.path.join(HERE, 'Trash_Schedule_Website'), static_url_path='')
CORS(app)


@app.route('/')
def home_page():
    return app.send_static_file('index.html')


#The new design is at the root (index.html above); it was under /new/ for a day, so those
#links go to the same page at the root. nginx does the same, see deploy/nginx-*.conf
@app.route('/new/')
@app.route('/new/<path:page>')
def old_new_design_link(page=''):
    return redirect('/' + ('' if page == 'index.html' else page), code=301)


#The classic design. nginx finds classic/index.html by itself, Flask needs to be told


@app.route('/classic/')
def classic_home_page():
    return app.send_static_file('classic/index.html')


#The web page asks for this when it opens
@app.route('/config', methods=['GET'])
def handle_config():
    return jsonify({
        #The Google Maps key is not a secret, every visitor's browser needs it. It
        #is kept out of GitHub so that each server can use its own, see the README.
        'googleMapsKey': os.environ.get('GOOGLE_MAPS_API_KEY', ''),
        'towns': [{'id': town['id'], 'name': town['name']}
                  for town in sorted(towns.values(), key=lambda town: town['name'])],
    })


#This section of code is executed when you press the "check trash" button on the front end
@app.route('/data', methods=['POST'])
def handle_data():
    #The front end sends the parts of the address separately:
    #   {"house_number": "132", "street": "Elm Street", "town": "Elizabeth", "zip": "07208"}
    #The first version of the page sent one line of text, which still works:
    #   {"key": "132 Elm Street 07208"}
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return problem("Enter a street address.")

    if isinstance(data.get('key'), str):
        pieces = data['key'].replace(',', ' ').split()
        if len(pieces) < 3:
            return problem("Enter the house number, street name and ZIP code, for example: 132 Elm Street 07208")
        house_number, street, town_name, zip_code = pieces[0], ' '.join(pieces[1:-1]), '', pieces[-1]
        if not normalize_zip(zip_code) or len(zip_code) != 5:
            return problem("The address must end with a 5 digit ZIP code, for example: 132 Elm Street 07208")
    else:
        house_number = str(data.get('house_number') or '').strip()
        street = str(data.get('street') or '').strip()
        town_name = str(data.get('town') or '').strip()
        zip_code = str(data.get('zip') or '').strip()

    if not (house_number.isascii() and house_number.isdigit()):
        return problem("The address needs a house number, for example: 132 Elm Street")
    if not street:
        return problem("Enter the street name.")
    if zip_code and not normalize_zip(zip_code):
        return problem("The ZIP code must be 5 digits, for example: 07208")
    zip_code = normalize_zip(zip_code)

    town = schedule.find_town(towns, town_name, zip_code)
    if town is None:
        where = town_name or (("ZIP code " + zip_code) if zip_code else "That town")
        return problem("%s is not covered yet. The towns we cover are: %s." % (where, town_names()), 404)

    #Some streets go by two names, the town file says which one the table uses
    street = town.get('street_names', {}).get(normalize_street(street), street)
    #A street with an East and a West part (Roselle's avenues). Google often leaves the
    #E or W out, so the page also sends the map location Google gave for the address.
    location = None
    if isinstance(data.get('location'), dict):
        try:
            location = (float(data['location']['lat']), float(data['location']['lng']))
        except (KeyError, TypeError, ValueError):
            location = None
        if location and not (-90 <= location[0] <= 90 and -180 <= location[1] <= 180):
            location = None
    found = addresses.find_on_split_street(town['id'], int(house_number), street, zip_code,
                                           town.get('direction_split'), location)
    if found is None:
        found = addresses.find(town['id'], int(house_number), street, zip_code)
    if found is None:
        return problem("We could not find that address in %s. Check the house number, street name and ZIP code." % town['name'], 404)

    #The page may ask for another date to look at a different week
    today = datetime.datetime.now(NEW_JERSEY).date()
    if data.get('date'):
        try:
            today = schedule.parse_date(str(data['date']))
        except ValueError:
            return problem("The date must look like 2026-11-26.")

    #The Previous week and Next week buttons send how many weeks away to look:
    #1 is next week, -1 is last week. The page only offers a year each way.
    shown_date = today
    if data.get('week'):
        try:
            weeks_away = int(data['week'])
        except (TypeError, ValueError):
            return problem("The week must be a whole number, for example 1 for next week.")
        if not -52 <= weeks_away <= 52:
            return problem("We can only show weeks up to a year away.")
        shown_date = today + datetime.timedelta(weeks=weeks_away)

    notes = list(town.get('notes', []))
    contact = town.get('contact', 'your town')
    if found.get('how') == 'default':
        divider = town['direction_split'].get('divider', 'the dividing street')
        notes.insert(0, "Your street has an East and a West part and the address did not say which, "
                        "so we used the West part (west of %s). If you live east of %s, look up the address "
                        "with an E in front of the street name. Please confirm your days with %s." % (divider, divider, contact))
    elif found['needs_check']:
        notes.insert(0, "Your address is on or near the border between two pickup areas, so this is our best match. Please confirm your days with %s." % contact)
    if 'checked_through' in town and shown_date > schedule.parse_date(town['checked_through']):
        notes.insert(0, "We have not checked %s's schedule past %s yet. Please confirm your days with %s." % (
            town['name'], town['checked_through'][:4], contact))

    #The new design also asks how many of the next pickups to list (1 to 60, 4 if not given)
    wanted = data.get('upcoming', 4)
    if isinstance(wanted, bool) or not isinstance(wanted, int) or not 1 <= wanted <= 60:
        return problem("upcoming must be a whole number from 1 to 60.")

    answer = schedule.week_schedule(town, found['zone'], shown_date)
    #Counted from the real date, not from the week shown
    answer['upcoming'] = schedule.upcoming(town, found['zone'], today, wanted)
    #today stays the real date, the days in the answer carry the dates of the week shown
    answer['today'] = today.isoformat()
    answer['town'] = {'id': town['id'], 'name': town['name']}
    #The full address as found, so the new design can show "Kenilworth, NJ 07033" even
    #when the visitor left the ZIP code out. Every town covered is in New Jersey.
    answer['address'] = {'zip': found['zip'] or zip_code, 'state': 'NJ'}
    #When the E or W was worked out, the street with it ("W 7th Ave"), so the page saves that
    if found.get('how') in ('number', 'location', 'default', 'nearest') and found['street'][:2] in ('E ', 'W '):
        answer['address']['street'] = found['street'][0] + ' ' + street
    answer['zone'] = {'id': found['zone'], 'word': town['zone_word'], 'label': town['zones'].get(found['zone'], found['zone'])}
    answer['notes'] = notes
    return jsonify(answer)


#Main
if __name__ == '__main__':
    load_everything()
    serve(app, host = "127.0.0.1", port = int(os.environ.get('PORT', '5000')))
