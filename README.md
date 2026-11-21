<!--# TrashScheduleNJ.com
Never forget your trash schedule again with https://trashschedulenj.com!

## Towns Supported 
* Elizabeth, New Jersey
* Kenilworth, New Jersey incoming...

## Contact Information
Jesse: Jessebalves@gmail.com  
Daniel: daniel.lordelo@yahoo.com

## Instructions to Run (Development)
1) First, test_server.py must be running at all times to recieve requests from the front end and access the MySQL database
2) After test_server is running, open index.html using Visual Studio Code's extenstion live server.
 
## Resources
HTML & CSS video: https://www.youtube.com/watch?v=HGTJBPNC-Gw&list=PLZPZq0r_RZOPP5Yjt6IqgytMRY5uLt4y3  

JavaScript video: https://www.youtube.com/watch?v=lfmg-EJ8gm4&list=PLZPZq0r_RZOPP5Yjt6IqgytMRY5uLt4y3&index=2  

React video: https://www.youtube.com/watch?v=CgkZ7MvWUAA&list=PLZPZq0r_RZOPP5Yjt6IqgytMRY5uLt4y3&index=3  

MongoDB video: https://www.youtube.com/watch?v=c2M-rlkkT5o&list=PLZPZq0r_RZOPP5Yjt6IqgytMRY5uLt4y3&index=4  

MySQL video: https://www.youtube.com/watch?v=5OdVJbNCSso&list=PLZPZq0r_RZOPP5Yjt6IqgytMRY5uLt4y3&index=5  

PHP video: https://www.youtube.com/watch?v=zZ6vybT1HQs&list=PLZPZq0r_RZOPP5Yjt6IqgytMRY5uLt4y3&index=6 
  
Flask tutorial (Python backend) : https://www.geeksforgeeks.org/flask-tutorial/-->

# TrashScheduleNJ

<details>
<summary>Table of Contents</summary>
  
- [Summary](#summary)
- [Features](#features)
- [Visuals](#visuals)
- [Technologies](#technologies)
- [What I Learned](#what-i-learned)
- [Setup and Installation](#setup-and-installation)
- [Usage](#usage)
- [Code Examples](#code-examples)
- [How to Contribute](#how-to-contribute)
- [Contact](#contact)
- [Acknowledgments](#acknowledgments)

</details>

## Summary
*Missed garbage day? Never forget your trash schedule again with https://trashschedulenj.com! This project is for residents of Union County, New Jersey to check their trash schedule for the week. Elizabeth and Kenilworth are covered so far, more towns are being added.*

## Features
<!--List the standout features of your project and what makes it unique.-->
- **Garbage Check**: Start typing your address and pick it from the Google Maps list, or type it in yourself, to check your trash schedule.
- **More than one town**: Each town has its own pickup types, days and holiday rules.
- **Holiday Check**: System accounts for holidays and garbage pickup date changes due to holidays.
- **Reset Table**: Reset the entire table to the initial state using the reset button.

## Visuals
<!--*Insert images or gifs showing your project in action. Consider before/after shots, workflows, or demos.*-->
<img width="1096" height="612" alt="traaaash" src="https://github.com/user-attachments/assets/2d44d0b0-54e4-42f0-a29c-56a12c24d355" />


## Technologies
<!--Detail the technologies, languages, frameworks, and tools used in the project.-->
- HTML
- CSS
- JavaScript
- Python
- Flask
- SQL
- MySQL Workbench
- DigitalOcean
- CloudFlare

## What I Learned
<!-- Highlight specific skills or concepts you learned or improved upon while working on this project. This section should directly address potential employer interests. -->
- **Flask**: Connected our frontend to our backend using a web framework and Python.
- **Database Connectivity**: Setting up and connecting a database that allows for data retrieval from the frontend.
- **Server Deployment and Configuration**: Setting up a Linux cloud server using Digital Ocean to serve web contents to clients.
- **Assigning a Domain Name**: Using CloudFlare to claim and assign a domain name to a specified Internet Protocol Address.

## Setup and Installation
<!--*Provide a clear, step-by-step guide to set up the project locally.*-->
1. Clone the repo: `git clone https://github.com/Jessebalves/TrashScheduleNJ.git`
2. Install Visual Studio Code.
3. Once installed, navigate to extensions. Download the extension named Live Server to view live changes made to the code base.
4. Right click on the file you want to open with Live Server, then select the Live Server option to view live changes. 

### Server install (Ubuntu)
`install.sh` sets up everything the live site needs on a fresh Ubuntu server (tested on 26.04 LTS): the system packages, a Python virtual environment, the MySQL database and address table, the `python_server` service and the nginx site.

1. Clone the repo on the server: `git clone https://github.com/Jessebalves/TrashScheduleNJ.git`
2. Run the installer: `cd TrashScheduleNJ && sudo ./install.sh`
3. If MySQL root already has a password, pass it in: `sudo MYSQL_ROOT_PASSWORD='...' ./install.sh`

To update the server later, run `./update.sh` from the checkout. It pulls the latest commits for the current branch and runs the installer again. It builds the address table again only when the files in `data/` have changed (or `REIMPORT=1` is set). When running `./update.sh` you will be prompted for the MySQL Root password.

Not automated: DNS records and the TLS certificate. Place the certificate and key at `/etc/ssl/cert.pem` and `/etc/ssl/key.pem`, then run `install.sh` again to switch nginx to HTTPS. Until then the site is served over HTTP.

Database credentials are never stored in the repo. The installer creates a read-only MySQL user for the web server and writes its password to `/etc/trashschedulenj/trashschedule.env`. 

To remove the site, run `sudo ./uninstall.sh` (it lists what it will remove and asks first; `sudo DRY_RUN=1 ./uninstall.sh` only shows it). It removes the service, the nginx site, the code, the venv, `/etc/trashschedulenj`, and the MySQL database and user (`KEEP_DATABASE=1` keeps them). nginx and MySQL themselves stay installed unless `REMOVE_PACKAGES=1` is set. That option purges every MySQL database and nginx site on the server.

### Google Maps address search
The home page lets visitors pick their address from a Google Maps list. This needs a Google Maps API key:

1. In the Google Cloud console, create a key and turn on **Maps JavaScript API** and **Places API (New)** for it.
2. Restrict the key to your website (HTTP referrer `https://trashschedulenj.com/*`) and to those two APIs. The key is sent to every visitor's browser, the restriction is what stops other websites from using it.
3. Give it to the installer once, it is remembered after that: `sudo GOOGLE_MAPS_API_KEY='...' ./install.sh`

The key is stored in `/etc/trashschedulenj/trashschedule.env`, not in the repo. Without a key the page shows boxes to type the house number, street and town in instead.

### Running it on your own computer
No database is needed for development. This reads the addresses straight from the `data/` folder:

```
pip install -r requirements.txt
ADDRESS_SOURCE=csv python3 test_server.py
```

Then open http://127.0.0.1:5000 in your browser. Run the tests with `python3 -m unittest discover tests`.

### Adding a town
A town is two files and no code, see [towns/README.md](towns/README.md):

- `towns/<town>.json`: the pickup types, days, holidays and notes
- `data/<town>.csv`: the streets and which ward or route each one is on

## Usage
*This project has limited usage due to restricted API keys and security behind our own database. Users can connect their own database through the python file running flask.*

## Code Examples
<!-- *Show small, but significant snippets of code from your project.* -->
<img width="598" height="812" alt="Screenshot 2026-08-07 131721" src="https://github.com/user-attachments/assets/360b9c12-0eaf-4b01-9e45-fbe4ffc56df0" />


## How to Contribute
<!--*Encourage contributions and provide guidelines for how others can help.*-->
Our system uses Flask on the backend. The easiest way to help is to add your town: write its rules in `towns/<town>.json` and its street list in `data/<town>.csv`, as described in [towns/README.md](towns/README.md). A new pickup type, such as grass and leaves, is one more entry in the town's file and shows up as its own row in the table.

## Contact
<!--- *First and last name* - *Email address*-->
- *Jesse Alves* - *jessebalves@gmail.com*
- *Daniel Lordelo* - *daniellordelo@gmail.com*
<!--- *Any other contact information*-->

## Acknowledgments
<!--*Credits to individuals or resources that helped you during the project.*-->
- elizabethnj.org : https://www.elizabethnj.org/288/Garbage-and-Recycling-Calendar
- Borough of Kenilworth, 2026 Information Guide DPW : https://kenilworthborough.com/188/Public-Works
- Aberdeen Township, 2026 Community Calendar (Trash & Recycling Pick-Up Schedule) : https://aberdeennj.org/271/Trash-Recycling
- Borough of Roselle, 2026/2027 Sanitation/Recycling Schedule (DPW) : https://www.boroughofroselle.com/departments/public_works/index.php
- Borough of Roselle Park, 2026 Curbside Collection Calendar (DPW) : https://www.rosellepark.gov/207/Recycling-Bulk-Waste-Calendar
- Township of Cranford, 2026 Curbside Recycling Calendar and Zones (DPW, Giordano) : https://www.cranfordnj.org/2413/Curbside-Recycling
- Town of Westfield, 2026 Curbside Recycling Schedule and Recycling Collection Zones map : https://www.westfieldnj.gov/189/Recycling-Schedule
- Township of Clark, 2026 Recycling Schedule, Bulky Pickup and the township's zone and ward map : https://www.ourclark.com/175/Recycling-Schedule
- Union County Board of Elections, "Find your Ward and District" street list : https://ucnj.org/boe/where-do-i-vote/
- US Census Bureau, TIGER/Line address ranges and town boundaries : https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html
---
