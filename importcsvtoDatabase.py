#!/usr/bin/env python3
"""Turn the county street list CSV into SQL for the `addresses` table.

The script only uses the Python standard library and prints SQL to stdout,
so it can be piped straight into the mysql client:

    python3 importcsvtoDatabase.py | sudo mysql trashschedule

install.sh does this automatically when the table is empty. The SQL replaces
the contents of the table, so running it twice does not duplicate rows.
"""
import csv
import os
import sys

DEFAULT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'countystreetlist04032017.csv')


def quote(text):
    """Quote a string as a MySQL literal."""
    return "'" + str(text).replace('\\', '\\\\').replace("'", "''") + "'"


def main():
    csv_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV
    rows = []
    skipped = 0

    #utf-8-sig drops the byte order mark at the start of the county file
    with open(csv_file, newline='', encoding='utf-8-sig') as handle:
        for row in csv.DictReader(handle):
            try:
                rows.append("(%s, %d, %d, %s, %s, %d)" % (
                    quote(row['Street_Name'].strip()),
                    int(row['Low_Range']),
                    int(row['High_Range']),
                    quote(row['Side'].strip()),
                    quote(row['ZIP'].strip()),
                    int(row['Ward']),
                ))
            except (KeyError, ValueError, AttributeError):
                #Rows with a missing or invalid number or ward are left out
                skipped += 1

    if not rows:
        sys.exit("No usable rows found in " + csv_file)

    print("""CREATE TABLE IF NOT EXISTS addresses (
    Street_Name VARCHAR(100),
    Low_Range INT,
    High_Range INT,
    Side CHAR(1),
    ZIP VARCHAR(10),
    Ward INT
);""")
    print("START TRANSACTION;")
    print("DELETE FROM addresses;")
    for start in range(0, len(rows), 500):
        print("INSERT INTO addresses (Street_Name, Low_Range, High_Range, Side, ZIP, Ward) VALUES")
        print(",\n".join(rows[start:start + 500]) + ";")
    print("COMMIT;")

    print("Rows written: %d, rows skipped: %d" % (len(rows), skipped), file=sys.stderr)


if __name__ == '__main__':
    main()
