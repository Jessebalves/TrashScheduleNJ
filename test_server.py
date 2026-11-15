#imports
import os
#used to send recieve requests and send back data
from flask import Flask, request, jsonify # type: ignore
from flask_cors import CORS # type: ignore
from waitress import serve #type: ignore
#Connects test_server.py to the MySQL database
import mysql.connector # type: ignore


#Every way of writing a street type is turned into one spelling, so that
#"Terrace", "terr." and "TER" all match. The same table is applied to the
#street names from the database, which is why LA and LN can share a spelling.
STREET_TYPES = {
    'STREET': 'ST', 'ST': 'ST', 'STR': 'ST',
    'ROAD': 'RD', 'RD': 'RD',
    'BOULEVARD': 'BLVD', 'BLVD': 'BLVD',
    'AVENUE': 'AVE', 'AVE': 'AVE', 'AV': 'AVE',
    'PLACE': 'PL', 'PL': 'PL',
    'DRIVE': 'DR', 'DR': 'DR',
    'TERRACE': 'TER', 'TER': 'TER', 'TERR': 'TER',
    'COURT': 'CT', 'CT': 'CT',
    'LANE': 'LN', 'LN': 'LN', 'LA': 'LN',
    'CIRCLE': 'CIR', 'CIR': 'CIR',
    'WAY': 'WAY',
    'PARKWAY': 'PKWY', 'PKWY': 'PKWY',
    'PLAZA': 'PLZ', 'PLZ': 'PLZ',
    'MANOR': 'MNR', 'MNR': 'MNR',
}

#Filled in by load_addresses() when the server starts.
#Each entry is (street name, low number, high number, side, zip code, ward)
addresses = []


def normalize_street(name):
    """Upper case a street name, drop dots and commas, and use one spelling for the street type."""
    words = [word.strip('.,').upper() for word in name.split()]
    words = [word for word in words if word]
    if words:
        words[-1] = STREET_TYPES.get(words[-1], words[-1])
    return ' '.join(words)


def load_addresses():
    """Read the whole address table into memory. Restart the service after changing the table."""
    #Database credentials come from environment variables so that no password
    #is stored in this file or in GitHub. In production install.sh writes them to
    #/etc/trashschedulenj/trashschedule.env and the python_server systemd service
    #loads that file. For development, export them in your shell before running:
    #   export DB_USER=... DB_PASSWORD=... DB_NAME=trashschedule
    dataBase = mysql.connector.connect(
        host = os.environ.get('DB_HOST', 'localhost'),
        user = os.environ.get('DB_USER', 'trashschedule'),
        password = os.environ['DB_PASSWORD'],
        database = os.environ.get('DB_NAME', 'trashschedule')
        )
    cursor = dataBase.cursor()
    print("Connection to MYSQL database running on", os.environ.get('DB_HOST', 'localhost'))
    cursor.execute("SELECT Street_Name, Low_Range, High_Range, Side, ZIP, Ward FROM addresses")
    for street, low, high, side, zip_code, ward in cursor.fetchall():
        #The county file stores zip codes without the leading zero (7208)
        addresses.append((normalize_street(street), low, high, side, str(zip_code).strip().zfill(5), ward))
    print("Address rows loaded:", len(addresses))
    cursor.close()
    dataBase.close()


def bad_request(message):
    """Answer with HTTP 400 and a message the front end shows to the visitor."""
    return jsonify({'error': message}), 400


#Flask
app = Flask(__name__)
CORS(app)

#This section of code is executed when you press the "check trash" button on the front end
@app.route('/data', methods=['POST'])
def handle_data():
    #The front end sends {"key": "132 Elm Street 07208"}
    data = request.get_json(silent=True)
    address = data.get('key') if isinstance(data, dict) else None
    if not isinstance(address, str) or not address.strip():
        return bad_request("Enter a street address, for example: 132 Elm Street 07208")

    pieces = address.replace(',', ' ').split()
    if len(pieces) < 3:
        return bad_request("Enter the house number, street name and ZIP code, for example: 132 Elm Street 07208")

    house_number = pieces[0]
    zip_code = pieces[-1]
    street = normalize_street(' '.join(pieces[1:-1]))

    if not (house_number.isascii() and house_number.isdigit()):
        return bad_request("The address must start with a house number, for example: 132 Elm Street 07208")
    if not (zip_code.isascii() and zip_code.isdigit() and len(zip_code) == 5):
        return bad_request("The address must end with a 5 digit ZIP code, for example: 132 Elm Street 07208")
    if not street:
        return bad_request("Enter the street name between the house number and the ZIP code.")

    house_number = int(house_number)
    side = "E" if house_number % 2 == 0 else "O"
    ward_number = 0

    for x in addresses:
        if street != x[0]:
            continue
        if x[1] > house_number:
            continue
        if house_number > x[2]:
            continue
        if zip_code != x[4]:
            continue
        if side == x[3]:
            ward_number += x[5]

    #Return back to the front end
    if 0 < ward_number:
        return jsonify(ward_number)
    else:
        return jsonify('error')


#Main
if __name__ == '__main__':
    load_addresses()
    serve(app, host = "127.0.0.1", port = int(os.environ.get('PORT', '5000')))
