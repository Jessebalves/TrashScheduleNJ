//The page asks test_server.py two things:
//   GET  /config   which towns are covered, and the Google Maps key if there is one
//   POST /data     the pickups for one address for this week
//
//All the rules (which ward or route is picked up on which day, holidays, paper
//and metal weeks) live on the server in the towns/ folder. This file only draws
//what the server answers, so a new town needs no changes here.

const dayNames = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

//Google only offers addresses inside this box, which is Union County with a little room around it
const unionCounty = { west: -74.47, south: 40.57, east: -74.13, north: 40.76 };

//The address of the last lookup and the week on screen (0 = this week, 1 = next
//week, -1 = last week), used by the Previous week and Next week buttons
let lastAddress = null;
let weekShown = 0;

//------------------------------------------Messages under the form------------------------------------------------------------>
//Shows a message under the form, pass "" to clear it
function showMessage(text){
    document.getElementById("com2").textContent = text;
}

//Shows today's date. The server sends its date with every answer ("2026-11-16"),
//before the first lookup the date of the visitor's own computer is used
function showDate(isoDate){
    let date = new Date();
    if(isoDate){
        const parts = isoDate.split("-");
        date = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    }
    const full_date = (date.getMonth() + 1) + "/" + date.getDate() + "/" + date.getFullYear();
    document.getElementById("displayed_date").textContent = "Date: " + dayNames[date.getDay()] + " " + full_date;
}

//Tells the visitor their address could not be used: empties the table, shows
//the reason under the form and opens a browser pop-up window
function showAddressError(reason){
    clearResult();
    showMessage(reason);
    window.alert("There was an error processing the address you entered.\n\n" + reason);
}

//------------------------------------------The table-------------------------------------------------------------------------->
//Adds one row to the table. cells is a list of 7 texts, Sunday first
function addRow(label, cells){
    const row = document.createElement("tr");
    row.style.backgroundColor = "aliceblue";
    const name = document.createElement("th");
    name.textContent = label;
    row.appendChild(name);
    cells.forEach(text => {
        const cell = document.createElement("th");
        cell.textContent = text;
        row.appendChild(cell);
    });
    document.getElementById("schedule_rows").appendChild(row);
}

//Puts the page back to how it looks before a lookup
function clearResult(){
    document.getElementById("schedule_rows").innerHTML = "";
    addRow("Pickups", ["-", "-", "-", "-", "-", "-", "-"]);
    document.getElementById("found_place").textContent = "";
    document.getElementById("com3").textContent = "";
    document.getElementById("town_notes").innerHTML = "";
    document.getElementById("week_buttons").hidden = true;
    showMessage("");
    showDate("");
}

//Turns "2026-11-26" into "11/26/2026"
function shortDate(isoDate){
    const parts = isoDate.split("-");
    return Number(parts[1]) + "/" + Number(parts[2]) + "/" + parts[0];
}

//Draws the server's answer for one address
//   X  there is a pickup that day
//   H  the day is a holiday
//   -  nothing that day
function showSchedule(answer){
    clearResult();
    document.getElementById("schedule_rows").innerHTML = "";

    answer.streams.forEach(stream => {
        const cells = answer.days.map(day => {
            if(day.holiday){
                return "H";
            }
            return stream.pickups.includes(day.name) ? "X" : "-";
        });
        addRow(stream.label, cells);
    });

    //Ex. "Elizabeth - Ward: Ward 4" or "Kenilworth - Garbage route: Tuesday & Friday"
    document.getElementById("found_place").textContent =
        answer.town.name + " - " + answer.zone.word + ": " + answer.zone.label.replace(answer.zone.word + " ", "");
    //Another week than this one: say which week the table is showing
    if(weekShown == 0){
        showDate(answer.today);
    }
    else{
        document.getElementById("displayed_date").textContent =
            "Week of " + shortDate(answer.days[0].date) + " to " + shortDate(answer.days[6].date);
    }
    document.getElementById("week_buttons").hidden = false;
    document.getElementById("this_week").disabled = (weekShown == 0);

    //Holidays this week, ex. "Thanksgiving is on Thursday!"
    const holidays = answer.days.filter(day => day.holiday).map(day => day.holiday + " is on " + day.name + "!");
    document.getElementById("com3").textContent = holidays.join(" ");

    //Pickups a holiday moved or cancelled, then the town's reminders
    showMessage(answer.changes.join(" "));
    const notes = document.getElementById("town_notes");
    answer.notes.forEach(text => {
        const item = document.createElement("li");
        item.textContent = text;
        notes.appendChild(item);
    });
}

//------------------------------------------Asking the server------------------------------------------------------------------>
//address is {house_number, street, town, zip}
//week is which week to show, 0 or left out for this week
function lookUp(address, week){
    lastAddress = address;
    weekShown = week || 0;
    fetch('/data', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(Object.assign({}, address, {week: weekShown}))
    })
    .then(response => response.json().then(data => ({ok: response.ok, data: data})))
    .then(answer => {
        //The server did not find the address or could not use it, and says why
        if(!answer.ok){
            showAddressError(answer.data.error || "Something went wrong, please try again later.");
        }
        else{
            showSchedule(answer.data);
        }
    })
    .catch(error => {
        //The server could not be reached or did not send back a usable answer
        console.log("error", error);
        showAddressError("Something went wrong, please try again later.");
    });
}

//------------------------------------------Google Maps address search--------------------------------------------------------->
//Shows the boxes for typing the address in by hand
function showTyping(){
    document.getElementById("typing_box").hidden = false;
}

//Loads Google Maps. The key comes from the server, so it is not written in this file
function loadGoogleMaps(key){
    return new Promise((resolve, reject) => {
        window.googleMapsIsReady = resolve;
        //Google calls this when the key is wrong or not allowed on this website
        window.gm_authFailure = () => reject(new Error("Google Maps did not accept the key"));
        const script = document.createElement("script");
        script.src = "https://maps.googleapis.com/maps/api/js?key=" + encodeURIComponent(key)
            + "&v=weekly&loading=async&libraries=places&callback=googleMapsIsReady";
        script.onerror = () => reject(new Error("Google Maps could not be loaded"));
        document.head.appendChild(script);
    });
}

//Google describes an address as a list of parts, each with a list of types.
//Returns the text of the first part of the wanted type, or ""
function addressPart(place, type, short){
    const part = (place.addressComponents || []).find(component => component.types.includes(type));
    if(!part){
        return "";
    }
    return short ? part.shortText : part.longText;
}

//Runs when the visitor picks an address from Google's list
async function addressPicked(placePrediction){
    const place = placePrediction.toPlace();
    await place.fetchFields({ fields: ["addressComponents"] });

    const address = {
        house_number: addressPart(place, "street_number", false),
        street: addressPart(place, "route", true),
        //A few places have no "locality", Google files their town under a sublocality
        town: addressPart(place, "locality", false) || addressPart(place, "sublocality_level_1", false),
        zip: addressPart(place, "postal_code", false)
    };

    //Fill the typing boxes in as well, so the visitor can see and correct what was sent
    document.getElementById("house_number").value = address.house_number;
    document.getElementById("street").value = address.street;
    document.getElementById("zip").value = address.zip;
    const townList = document.getElementById("town");
    const option = Array.from(townList.options).find(o => o.textContent == address.town);
    if(option){
        townList.value = option.value;
    }

    if(address.house_number == ""){
        showTyping();
        showAddressError("Pick an address that has a house number, or type the house number in.");
        return;
    }
    lookUp(address);
}

async function startGoogleSearch(key){
    await loadGoogleMaps(key);
    await google.maps.importLibrary("places");

    const search = new google.maps.places.PlaceAutocompleteElement({
        includedRegionCodes: ["us"],
        includedPrimaryTypes: ["street_address", "premise", "subpremise"],
        locationRestriction: unionCounty
    });
    search.addEventListener("gmp-select", event => {
        addressPicked(event.placePrediction).catch(error => {
            console.log("error", error);
            showTyping();
            showMessage("We could not read that address from Google. Please type it in below.");
        });
    });
    //Google refused a search, for example because the key is not allowed to use Places
    //or the key has used up its searches for the day
    search.addEventListener("gmp-error", () => {
        showTyping();
        //The notice goes above the search box, where the visitor is looking
        const notice = document.getElementById("search_notice");
        notice.textContent = "Address search is not available right now. Please type your address in below.";
        notice.hidden = false;
    });

    document.getElementById("google_search").appendChild(search);
    document.getElementById("google_box").hidden = false;
    document.getElementById("typing_box").hidden = true;
}

document.getElementById("show_typing").addEventListener('click', (c) => {
    c.preventDefault();
    showTyping();
    document.getElementById("house_number").focus();
});

//---------------------------------------------------------Previous week / This week / Next week buttons------------------------------------------------------------>
//Looks the same address up again for another week. The server shows at most a year each way
function changeWeek(week){
    if(lastAddress && week >= -52 && week <= 52){
        lookUp(lastAddress, week);
    }
}
document.getElementById("previous_week").addEventListener('click', () => changeWeek(weekShown - 1));
document.getElementById("this_week").addEventListener('click', () => changeWeek(0));
document.getElementById("next_week").addEventListener('click', () => changeWeek(weekShown + 1));

//---------------------------------------------------------Code snipped associated with submit button------------------------------------------------------------------->
//function associated with form on index.html
document.getElementById('test_server').addEventListener('submit', async (a) => {
    a.preventDefault();

    //The Check Trash button uses the typing boxes. With the Google search box the
    //lookup already runs when an address is picked, and the boxes hold that address
    const address = {
        house_number: document.getElementById("house_number").value.trim(),
        street: document.getElementById("street").value.trim(),
        town: document.getElementById("town").value,
        zip: document.getElementById("zip").value.trim()
    };
    if(address.house_number == "" || address.street == ""){
        showTyping();
        showAddressError("Enter your house number and street name.");
        return;
    }
    lookUp(address);
})


//---------------------------------------------------------Code snipped associated with reset button------------------------------------------------------------------->
document.getElementById("test_server").addEventListener('reset', async(b) =>{
    b.preventDefault();
    clearResult();
    document.getElementById("house_number").value = "";
    document.getElementById("street").value = "";
    document.getElementById("zip").value = "";
    const search = document.querySelector("#google_search gmp-place-autocomplete");
    if(search){
        search.value = "";
    }
})
//-------------------------------------------------------------------------------------------------------------------------------------------------------------------->

//---------------------------------------------------------Runs when the page opens--------------------------------------------------------------------------------->
clearResult();

fetch('/config')
    .then(response => response.json())
    .then(config => {
        //The list of towns for the Town box
        const townList = document.getElementById("town");
        config.towns.forEach(town => {
            const option = document.createElement("option");
            option.value = town.name;
            option.textContent = town.name;
            townList.appendChild(option);
        });

        if(config.googleMapsKey){
            startGoogleSearch(config.googleMapsKey).catch(error => {
                //Without Google the page still works with the typing boxes
                console.log("error", error);
                document.getElementById("google_box").hidden = true;
                showTyping();
            });
        }
    })
    .catch(error => {
        console.log("error", error);
        showMessage("The server could not be reached, please try again later.");
    });
