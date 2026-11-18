//The classic home page, as it looked on the main branch: one "Street Address" box and a
//Sunday to Saturday table with an X on each pickup day and an H on a holiday.
//
//The page and its look are main's. This script is new: main's index.js asked a server on
//the visitor's own computer (localhost) and worked out Elizabeth's days itself. Now the
//server works out every town's week (towns/ folder), and this only draws its answer:
//   POST /data  {"key": "132 Elm Street 07208"}   the one-line address, as main sent it

const dayNames = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const table = document.getElementById("trash_table");

//The rows the page starts with (Paper, Metal, Garbage with a dash every day), for Reset
const firstRows = Array.from(table.rows).slice(1).map(row => row.cloneNode(true));

//------------------------------------------Messages under the buttons-------------------------------------------------------->
function setText(id, text){
    document.getElementById(id).textContent = text;
}

//"Date: Wednesday 11/18/2026". isoDate is the server's date ("2026-11-18"), before the
//first lookup the visitor's own computer's date is used, as on main
function showDate(isoDate){
    let date = new Date();
    if(isoDate){
        const parts = isoDate.split("-");
        date = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    }
    setText("displayed_date", "Date: " + dayNames[date.getDay()] + " " + (date.getMonth() + 1) + "/" + date.getDate() + "/" + date.getFullYear());
}

//------------------------------------------The table------------------------------------------------------------------------->
//Puts back the rows the page started with
function resetTable(){
    Array.from(table.rows).slice(1).forEach(row => row.remove());
    firstRows.forEach(row => table.tBodies[0].appendChild(row.cloneNode(true)));
}

//One row per kind of pickup, in the same style as main's rows. Elizabeth's are Paper, Metal
//and Garbage as before; another town gets its own rows (Kenilworth has four)
function showWeek(answer){
    Array.from(table.rows).slice(1).forEach(row => row.remove());
    answer.streams.forEach(stream => {
        const row = document.createElement("tr");
        row.style.backgroundColor = "aliceblue";
        const name = document.createElement("th");
        name.textContent = stream.label;
        row.appendChild(name);
        answer.days.forEach(day => {
            const cell = document.createElement("th");
            cell.textContent = day.holiday ? "H" : stream.pickups.includes(day.name) ? "X" : "-";
            row.appendChild(cell);
        });
        table.tBodies[0].appendChild(row);
    });
    //main's table ends with an empty row, which adds a little space under the last one
    table.tBodies[0].appendChild(document.createElement("tr"));
    showDate(answer.today);
    //Ex. "Thanksgiving is on Thursday!"
    setText("com3", answer.days.filter(day => day.holiday).map(day => day.holiday + " is on " + day.name + "!").join(" "));
    //Pickups a holiday moved, then anything the visitor should check with the town
    setText("com2", answer.changes.concat(answer.notes).join(" "));
}

//------------------------------------------Check Trash----------------------------------------------------------------------->
document.getElementById("test_server").addEventListener("submit", event => {
    event.preventDefault();
    const address = document.getElementById("address").value.trim();
    fetch("/data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: address })
    })
    .then(response => response.json().then(data => ({ ok: response.ok, data: data })))
    .then(answer => {
        if(!answer.ok){
            //The server says why, ex. "The address must end with a 5 digit ZIP code, for example: 132 Elm Street 07208"
            resetTable();
            setText("com3", "");
            setText("com2", answer.data.error || "Something went wrong, please try again later.");
            return;
        }
        showWeek(answer.data);
    })
    .catch(error => {
        console.error("Error:", error);
        resetTable();
        setText("com2", "Something went wrong, please try again later.");
    });
});

//------------------------------------------Reset----------------------------------------------------------------------------->
document.getElementById("test_server").addEventListener("reset", event => {
    event.preventDefault();
    resetTable();
    document.getElementById("address").value = "";
    setText("com2", "");
    setText("com3", "");
    showDate("");
});

showDate("");
