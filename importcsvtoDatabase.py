#!/usr/bin/env python3
"""Turn the address files in the data/ folder into SQL for the `addresses` table.

Every town has one file, data/<town>.csv, with these columns:

    Municipality, Street_Name, Low_Range, High_Range, Side, ZIP, Zone, Needs_Check

The script only uses the Python standard library and prints SQL to stdout,
so it can be piped straight into the mysql client:

    python3 importcsvtoDatabase.py | sudo mysql trashschedule

install.sh does this automatically whenever the files in data/ have changed.
The SQL builds the table again from nothing, so the data/ folder is the one
place to make changes: anything edited by hand in MySQL is lost on the next import.
"""
import csv
import os
import sys

DATA_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def quote(text):
    """Quote a string as a MySQL literal."""
    return "'" + str(text).replace('\\', '\\\\').replace("'", "''") + "'"


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else DATA_FOLDER
    rows = []
    skipped = 0

    for file_name in sorted(os.listdir(folder)):
        if not file_name.endswith('.csv'):
            continue
        #utf-8-sig drops the byte order mark some spreadsheet programs put at the start
        with open(os.path.join(folder, file_name), newline='', encoding='utf-8-sig') as handle:
            for row in csv.DictReader(handle):
                try:
                    if row['Side'].strip() not in ('E', 'O', 'B') or not row['Zone'].strip():
                        raise ValueError
                    rows.append("(%s, %s, %d, %d, %s, %s, %s, %s)" % (
                        quote(row['Municipality'].strip()),
                        quote(row['Street_Name'].strip()),
                        int(row['Low_Range']),
                        int(row['High_Range']),
                        quote(row['Side'].strip()),
                        quote(row['ZIP'].strip()),
                        quote(row['Zone'].strip()),
                        quote(row['Needs_Check'].strip()),
                    ))
                except (KeyError, ValueError, AttributeError):
                    #Rows with a missing or invalid number, side or zone are left out
                    skipped += 1

    if not rows:
        sys.exit("No usable rows found in " + folder)

    #The new table is filled under another name and swapped in at the end, so the
    #website never sees a half filled table
    print("DROP TABLE IF EXISTS addresses_new;")
    print("""CREATE TABLE addresses_new (
    Municipality VARCHAR(60),
    Street_Name VARCHAR(100),
    Low_Range INT,
    High_Range INT,
    Side CHAR(1),
    ZIP VARCHAR(10),
    Zone VARCHAR(20),
    Needs_Check VARCHAR(1)
);""")
    for start in range(0, len(rows), 500):
        print("INSERT INTO addresses_new (Municipality, Street_Name, Low_Range, High_Range, Side, ZIP, Zone, Needs_Check) VALUES")
        print(",\n".join(rows[start:start + 500]) + ";")
    print("DROP TABLE IF EXISTS addresses;")
    print("RENAME TABLE addresses_new TO addresses;")

    print("Rows written: %d, rows skipped: %d" % (len(rows), skipped), file=sys.stderr)


if __name__ == '__main__':
    main()
