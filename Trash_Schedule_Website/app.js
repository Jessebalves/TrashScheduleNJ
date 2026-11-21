//The new design of TrashScheduleNJ, at the root of the website (the classic one is in classic/).
//Every new design page loads this file; <body data-page="...">
//says which page it is: home, calendar, which-bin or settings.
//
//It talks to the same server as the classic page (index.js):
//   GET  /config   which towns are covered, and the Google Maps key if there is one
//   POST /data     the pickups for one address. The answer's "upcoming" part lists the next
//                  pickups and the holiday changes, see pickup_schedule.upcoming()
//
//How each pickup category looks (name, color, icon, short label) is not written here. It comes
//from data/counties/<county>.json, so a town with other categories needs no change to this file.
"use strict";

//------------------------------------------------------------------ saved settings
//Kept in the visitor's browser only
//   tsn.address     the address shown now
//   tsn.addresses   every address the visitor added (the drop-down under the address button).
//                   Switching between them only asks our own server, never Google, so it costs
//                   nothing on the Google Maps bill
const KEYS = { address: "tsn.address", addresses: "tsn.addresses", reminder: "tsn.reminder" };
const MAX_SAVED_ADDRESSES = 5;

const store = {
    get(key){
        try{ return JSON.parse(localStorage.getItem(key)); }
        catch(error){ return null; }
    },
    set(key, value){
        try{ localStorage.setItem(key, JSON.stringify(value)); }
        catch(error){ /* private window: works for this visit only */ }
    },
    remove(key){
        try{ localStorage.removeItem(key); }
        catch(error){ /* nothing to do */ }
    }
};

//------------------------------------------------------------------ small helpers
function esc(text){
    return String(text == null ? "" : text).replace(/[&<>"']/g, c =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

//Colors come from our own data files, but only a plain hex color is ever put in a style
function safeColor(color, fallback){
    return /^#[0-9a-f]{3,8}$/i.test(color || "") ? color : fallback;
}

const $ = (selector, root) => (root || document).querySelector(selector);

async function fetchJSON(url, options){
    const response = await fetch(url, options);
    let data = null;
    try{ data = await response.json(); }
    catch(error){ /* not JSON */ }
    return { ok: response.ok, status: response.status, data: data };
}

//------------------------------------------------------------------ icons (simple line icons)
const ICON_PATHS = {
    trash: '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>',
    recycle: '<path d="M7 19l-3-5 3-5"/><path d="M4 14h9"/><path d="M17 5l3 5-3 5"/><path d="M20 10h-9"/>',
    paper: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/><path d="M10 13h6"/><path d="M10 17h6"/>',
    can: '<ellipse cx="12" cy="5" rx="6" ry="2"/><path d="M6 5v14c0 1.1 2.7 2 6 2s6-.9 6-2V5"/><path d="M6 12c0 1.1 2.7 2 6 2s6-.9 6-2"/>',
    bottle: '<path d="M10 2h4v4l2 3v12a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V9l2-3z"/><path d="M8 13h8"/>',
    leaf: '<path d="M5 21c0-9 6-15 15-16-1 9-7 15-15 16z"/><path d="M5 21l8-8"/>',
    dropoff: '<circle cx="12" cy="12" r="9"/><path d="M12 7v6"/><path d="M12 16.5h.01"/>',
    bin: '<rect x="5" y="7" width="14" height="14" rx="2"/><path d="M3 7h18"/><path d="M10 4h4"/>',
    home: '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18"/><path d="M8 3v4"/><path d="M16 3v4"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    bell: '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0"/>',
    pin: '<path d="M12 21s-7-6.1-7-11a7 7 0 0 1 14 0c0 4.9-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    chevron: '<path d="M6 9l6 6 6-6"/>',
    alert: '<path d="M10.3 3.9L2 18a2 2 0 0 0 1.7 3h16.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    download: '<path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M5 20h14"/>',
    external: '<path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M18 14v6H4V6h6"/>',
    check: '<path d="M5 12l5 5 9-10"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    close: '<path d="M6 6l12 12"/><path d="M18 6L6 18"/>',
    plus: '<path d="M12 5v14"/><path d="M5 12h14"/>'
};

function icon(name, size, extra){
    return '<svg aria-hidden="true" focusable="false" width="' + (size || 20) + '" height="' + (size || 20)
        + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
        + (extra || "") + '>' + (ICON_PATHS[name] || ICON_PATHS.bin) + '</svg>';
}

//------------------------------------------------------------------ dates
//The server sends dates as "2026-11-19" in New Jersey time. They are handled as UTC
//days here so the visitor's own time zone and daylight saving time cannot shift them.
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December"];

function toDate(iso){
    const p = iso.split("-").map(Number);
    return new Date(Date.UTC(p[0], p[1] - 1, p[2]));
}
function daysBetween(fromIso, toIso){
    return Math.round((toDate(toIso) - toDate(fromIso)) / 86400000);
}
function weekday(iso){ return DAYS[toDate(iso).getUTCDay()]; }
function longDate(iso){
    const d = toDate(iso);
    return DAYS[d.getUTCDay()] + ", " + MONTHS[d.getUTCMonth()].slice(0, 3) + " " + d.getUTCDate();
}
function compact(iso){ return iso.replace(/-/g, ""); }
function nextDay(iso){
    const d = toDate(iso);
    d.setUTCDate(d.getUTCDate() + 1);
    return d.toISOString().slice(0, 10);
}

//------------------------------------------------------------------ county settings
//data/counties/index.json says which county a town is in; the county file says how each
//category looks; data/which-bin/<county>.json is the Which bin list.
let countyIndex = null;
const countyFiles = {};

async function loadCounty(townId){
    if(!countyIndex){
        const answer = await fetchJSON("data/counties/index.json");
        countyIndex = answer.ok ? answer.data : { default_county: "union", towns: {} };
    }
    const id = (townId && countyIndex.towns[townId]) || countyIndex.default_county;
    if(!countyFiles[id]){
        countyFiles[id] = Promise.all([
            fetchJSON("data/counties/" + encodeURIComponent(id) + ".json"),
            fetchJSON("data/which-bin/" + encodeURIComponent(id) + ".json")
        ]).then(([county, which]) => ({
            id: id,
            county: county.ok ? county.data : { categories: {} },
            which: which.ok ? which.data : null
        }));
    }
    return countyFiles[id];
}

//What one category looks like. label is the town's own name for it (from the server); without
//one the county file's name is used. Anything missing falls back to a neutral default.
const NEUTRAL = { color: "#5A615D", icon: "bin", short: "" };
function category(county, townId, id, label){
    const base = county.default_category || {};
    const own = (county.categories || {})[id] || {};
    const town = (((county.towns || {})[townId] || {}).categories || {})[id] || {};
    const merged = Object.assign({}, NEUTRAL, base, own, town);
    return {
        id: id,
        name: label || merged.name || id,
        color: safeColor(merged.color, NEUTRAL.color),
        icon: ICON_PATHS[merged.icon] ? merged.icon : "bin",
        short: merged.short || ""
    };
}

//------------------------------------------------------------------ talking to the server
let configPromise = null;
function getConfig(){
    if(!configPromise){
        configPromise = fetchJSON("/config").then(answer => answer.ok ? answer.data : { towns: [], googleMapsKey: "" })
            .catch(() => ({ towns: [], googleMapsKey: "", offline: true }));
    }
    return configPromise;
}

//address is {house_number, street, town, zip}; upcoming is how many pickups to list.
//location ({lat, lng}, from Google) tells the server E from W when Google leaves it out
//of a street name (Roselle's "152 7th Ave")
async function lookUp(address, upcoming, location){
    const body = {
        house_number: address.house_number, street: address.street,
        town: address.town || "", zip: address.zip || "", upcoming: upcoming || 4
    };
    if(location){
        body.location = location;
    }
    try{
        const answer = await fetchJSON("/data", {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
        });
        if(answer.ok && answer.data && answer.data.upcoming){
            return { ok: true, data: answer.data };
        }
        return { ok: false, error: (answer.data && answer.data.error) || "Something went wrong, please try again later." };
    }
    catch(error){
        console.log("error", error);
        return { ok: false, error: "The server could not be reached. Check your connection and try again.", offline: true };
    }
}

//------------------------------------------------------------------ the address
function savedAddress(){
    const a = store.get(KEYS.address);
    return a && a.house_number && a.street ? a : null;
}

function addressLine(a){
    return a ? (a.house_number + " " + a.street).trim() : "";
}

//"Kenilworth, NJ 07033". The ZIP code comes from the server when the visitor left it out
function townLine(a){
    if(!a.town) return a.zip || "";
    return (a.town + ", " + (a.state || "NJ") + " " + (a.zip || "")).trim();
}

//Puts the ZIP code and state from a server answer on a saved address (and its copy in the
//list), for addresses saved before the server sent them or typed in without a ZIP code
function completeAddress(address, answer){
    const found = answer.address || {};
    if(!found.zip || (address.zip === found.zip && address.state === found.state)){
        return;
    }
    const fill = a => sameAddress(a, address) ? Object.assign({}, a, { zip: found.zip, state: found.state || "NJ" }) : a;
    store.set(KEYS.addresses, savedAddresses().map(fill));
    const current = savedAddress();
    if(current){
        store.set(KEYS.address, fill(current));
    }
}

const sameText = (x, y) => String(x || "").trim().toUpperCase().replace(/\s+/g, " ")
    === String(y || "").trim().toUpperCase().replace(/\s+/g, " ");
function sameAddress(a, b){
    return sameText(a.house_number, b.house_number) && sameText(a.street, b.street) && sameText(a.town, b.town);
}

//The saved list, oldest first. An address saved before the list existed is put in it
function savedAddresses(){
    let list = store.get(KEYS.addresses);
    list = Array.isArray(list) ? list.filter(a => a && a.house_number && a.street) : [];
    const current = savedAddress();
    if(current && !list.some(a => sameAddress(a, current))){
        list.push(current);
    }
    return list;
}

//Makes an address the current one and adds it to the list if it is new. One already in the
//list keeps its place, so the drop-down does not reorder itself when you switch
function useAddress(address){
    let list = savedAddresses();
    const at = list.findIndex(a => sameAddress(a, address));
    if(at >= 0){
        list[at] = address;
    }
    else{
        list.push(address);
    }
    //Too many: drop the oldest that is not this one
    list = list.slice(-MAX_SAVED_ADDRESSES);
    store.set(KEYS.addresses, list);
    store.set(KEYS.address, address);
}

//Removes one address. If it was the current one, the most recent other one takes its place
function forgetAddress(address){
    const list = savedAddresses().filter(a => !sameAddress(a, address));
    store.set(KEYS.addresses, list);
    const current = savedAddress();
    if(current && sameAddress(current, address)){
        if(list.length){
            store.set(KEYS.address, list[list.length - 1]);
        }
        else{
            store.remove(KEYS.address);
        }
    }
}

//"Elizabeth · Ward 4" or "Kenilworth · Garbage route: Tuesday & Friday"
function placeLine(answer){
    const zone = answer.zone.label.indexOf(answer.zone.word) === 0
        ? answer.zone.label : answer.zone.word + ": " + answer.zone.label;
    return answer.town.name + " · " + zone;
}

//------------------------------------------------------------------ header, menus, footer
const PAGES = [
    { id: "home", href: "./", label: "Home", icon: "home" },
    { id: "calendar", href: "calendar.html", label: "Calendar", icon: "calendar" },
    { id: "which-bin", href: "which-bin.html", label: "Which bin", icon: "search" },
    { id: "settings", href: "settings.html", label: "Settings", icon: "settings" }
];

function renderChrome(page){
    const current = id => id === page ? ' aria-current="page"' : "";
    const header = document.createElement("header");
    header.className = "site-header";
    header.innerHTML =
        '<div class="header-inner">'
        + '<a class="brand" href="./"><span class="brand-mark">' + icon("trash", 20) + '</span>'
        + '<span class="brand-name">Trash &amp; Recycling</span></a>'
        + '<nav class="top-nav" aria-label="Main">'
        + PAGES.map(p => '<a href="' + p.href + '"' + current(p.id) + '>' + p.label + '</a>').join("")
        + '</nav>'
        + '<div class="address-block">'
        + '<span class="address-caption" aria-hidden="true">Your address</span>'
        + '<button type="button" class="address-button" id="address-button" aria-expanded="false" aria-controls="address-menu">'
        + '<span class="pin">' + icon("pin", 18) + '</span>'
        + '<span class="visually-hidden">Your address: </span>'
        + '<span class="address-text" id="address-text"></span>' + icon("chevron", 18) + '</button>'
        //The saved addresses drop-down, filled in by renderAddressMenu
        + '<div class="address-menu" id="address-menu" hidden></div>'
        + '</div>'
        + '<a class="icon-button bell" href="settings.html#remind-card" aria-label="Reminder settings">' + icon("bell", 20) + '</a>'
        + '</div>';
    document.body.insertBefore(header, $("main"));

    const nav = document.createElement("nav");
    nav.className = "bottom-nav";
    nav.setAttribute("aria-label", "Main");
    nav.innerHTML = PAGES.map(p => '<a href="' + p.href + '"' + current(p.id) + '>' + icon(p.icon, 24) + p.label + '</a>').join("");
    document.body.appendChild(nav);

    const footer = document.createElement("footer");
    footer.className = "site-footer";
    footer.innerHTML = 'TrashScheduleNJ · Always confirm holiday changes with your town. '
        + 'If the information shown is inaccurate, please send us an email via the Contact page. '
        + '<a href="classic/about.html">About</a> · <a href="classic/contact.html">Contact</a>';
    $("main").after(footer);

    $("#address-button").addEventListener("click", () => {
        //Nothing saved yet: go straight to the form
        if(!savedAddresses().length){
            toggleAddressPanel();
        }
        else{
            toggleAddressMenu();
        }
    });
    setupAddressMenu();
    showAddressInHeader();
}

function showAddressInHeader(){
    const a = savedAddress();
    $("#address-text").textContent = a ? addressLine(a) : "Add your address";
    $("#address-button").setAttribute("aria-controls", savedAddresses().length ? "address-menu" : "address-panel");
}

//------------------------------------------------------------------ saved addresses drop-down
//A list of buttons that opens under the address button (a disclosure, not an ARIA menu, so
//Tab and Enter work as everywhere else). Escape or a click outside closes it.
function savedListHTML(){
    const current = savedAddress();
    return savedAddresses().slice().reverse().map((a, n) => {
        const isCurrent = current && sameAddress(a, current);
        const name = addressLine(a) + ", " + townLine(a);
        return '<li class="saved-row">'
            + '<button type="button" class="saved-use" data-key="' + n + '"' + (isCurrent ? ' aria-current="true"' : '') + '>'
            + '<span class="saved-check">' + (isCurrent ? icon("check", 18) : '') + '</span>'
            + '<span class="saved-text"><span class="saved-line">' + esc(addressLine(a)) + '</span>'
            + '<span class="saved-town">' + esc(townLine(a)) + (isCurrent ? ' · <span>Showing now</span>' : '') + '</span></span></button>'
            + '<button type="button" class="saved-remove" data-key="' + n + '" aria-label="Remove ' + esc(name) + '">' + icon("close", 18) + '</button>'
            + '</li>';
    }).join("");
}

//The list is shown newest first; data-key is the position in that order
function addressFromKey(key){
    return savedAddresses().slice().reverse()[Number(key)];
}

function renderAddressMenu(){
    $("#address-menu").innerHTML =
        '<p class="menu-label" id="menu-label">Saved addresses</p>'
        + '<ul class="saved-list" aria-labelledby="menu-label">' + savedListHTML() + '</ul>'
        + '<button type="button" class="menu-add">' + icon("plus", 18) + 'Add a new address</button>';
}

function toggleAddressMenu(force){
    const menu = $("#address-menu");
    const button = $("#address-button");
    const open = force !== undefined ? force : menu.hidden;
    if(open){
        renderAddressMenu();
        //The form and the menu are never open together
        if(!$("#address-panel").hidden && savedAddress()){
            toggleAddressPanel(false);
        }
    }
    menu.hidden = !open;
    button.setAttribute("aria-expanded", open ? "true" : "false");
    if(open){
        const first = $('.saved-use[aria-current="true"]', menu) || $(".saved-use", menu);
        (first || $(".menu-add", menu)).focus();
    }
}

//Shared by the drop-down and the Settings page: "use" and "remove" buttons in a saved list
async function handleSavedClick(event, afterChange){
    const use = event.target.closest(".saved-use");
    const remove = event.target.closest(".saved-remove");
    if(use){
        const address = addressFromKey(use.dataset.key);
        const current = savedAddress();
        if(address && !(current && sameAddress(address, current))){
            useAddress(address);
            showAddressInHeader();
            afterChange("switched");
            pageState.reload();
        }
        else{
            afterChange("same");
        }
    }
    else if(remove){
        const address = addressFromKey(remove.dataset.key);
        if(!address){
            return;
        }
        const current = savedAddress();
        const wasCurrent = current && sameAddress(address, current);
        forgetAddress(address);
        showAddressInHeader();
        afterChange("removed", address);
        if(wasCurrent){
            pageState.reload();
        }
    }
}

function setupAddressMenu(){
    const menu = $("#address-menu");
    const button = $("#address-button");
    menu.addEventListener("click", event => {
        if(event.target.closest(".menu-add")){
            toggleAddressMenu(false);
            toggleAddressPanel(true);
            return;
        }
        handleSavedClick(event, (what, address) => {
            if(what === "removed" && savedAddresses().length){
                renderAddressMenu();
                const status = document.createElement("p");
                status.className = "menu-status";
                status.setAttribute("role", "status");
                status.textContent = "Removed " + addressLine(address) + ".";
                menu.prepend(status);
                $(".saved-use, .menu-add", menu).focus();
            }
            else{
                toggleAddressMenu(false);
                button.focus();
            }
        });
    });
    document.addEventListener("click", event => {
        //composedPath, not contains: Remove redraws the list, so the clicked button is gone by now
        const path = event.composedPath();
        if(!menu.hidden && !path.includes(menu) && !path.includes(button)){
            toggleAddressMenu(false);
        }
    });
    document.addEventListener("keydown", event => {
        if(event.key === "Escape" && !menu.hidden){
            toggleAddressMenu(false);
            button.focus();
        }
    });
}

//------------------------------------------------------------------ Google address search
//Same approach as the classic page: Google is only used when the server has a key, and the
//typed fields are always there as a fallback. Google is loaded only when the form is opened,
//because every keystroke in the search box counts against the key's daily limit.
const unionCounty = { west: -74.47, south: 40.57, east: -74.13, north: 40.76 };
let googlePromise = null;

function loadGoogleMaps(key){
    if(!googlePromise){
        googlePromise = new Promise((resolve, reject) => {
            window.googleMapsIsReady = resolve;
            window.gm_authFailure = () => reject(new Error("Google Maps did not accept the key"));
            const script = document.createElement("script");
            script.src = "https://maps.googleapis.com/maps/api/js?key=" + encodeURIComponent(key)
                + "&v=weekly&loading=async&libraries=places&callback=googleMapsIsReady";
            script.onerror = () => reject(new Error("Google Maps could not be loaded"));
            document.head.appendChild(script);
        }).then(() => google.maps.importLibrary("places"));
    }
    return googlePromise;
}

function addressPart(place, type, short){
    const part = (place.addressComponents || []).find(component => component.types.includes(type));
    return part ? (short ? part.shortText : part.longText) : "";
}

//------------------------------------------------------------------ the address form
//onSaved(answer) runs after the server found the address and it was saved
function buildAddressForm(panel, options){
    panel.innerHTML =
        '<h2 id="address-title">' + esc(options.title || "Find your pickup days") + '</h2>'
        + '<p class="muted" id="address-lead">Enter your street address.</p>'
        + '<form class="address-form" novalidate>'
        + '<div class="google-box" hidden>'
        + '<p class="field-label"><b>Start typing your address, then pick it from the list</b></p>'
        + '<p class="form-error search-notice"></p>'
        + '<div class="google-search"></div>'
        + '<button type="button" class="link-button show-typing">Type the address in yourself</button>'
        + '</div>'
        + '<div class="fields typing-box">'
        + '<div class="field"><label for="f-house">House number</label><input id="f-house" inputmode="numeric" autocomplete="off" placeholder="132"></div>'
        + '<div class="field field-wide"><label for="f-street">Street</label><input id="f-street" autocomplete="off" placeholder="Elm Street"></div>'
        + '<div class="field"><label for="f-town">Town</label><select id="f-town"></select></div>'
        + '<div class="field"><label for="f-zip">ZIP code (optional)</label><input id="f-zip" inputmode="numeric" maxlength="5" autocomplete="off" placeholder="07208"></div>'
        + '</div>'
        + '<p class="form-error" role="alert"></p>'
        + '<div class="button-row">'
        + '<button type="submit" class="button button-primary">Show my schedule</button>'
        + (options.cancellable ? '<button type="button" class="button cancel">Cancel</button>' : '')
        + '</div>'
        + '</form>';

    const form = $("form", panel);
    const error = $('[role="alert"]', panel);
    const submit = $('button[type="submit"]', panel);
    const fields = { house: $("#f-house", panel), street: $("#f-street", panel), town: $("#f-town", panel), zip: $("#f-zip", panel) };
    //The address last picked from Google search and its map location
    let picked = null;

    //The form always adds an address; saved ones are picked from the drop-down instead
    getConfig().then(config => {
        config.towns.forEach(town => {
            const option = document.createElement("option");
            option.value = town.name;
            option.textContent = town.name;
            fields.town.appendChild(option);
        });
        if(config.towns.length){
            $("#address-lead", panel).textContent = "We cover " + andList(config.towns.map(t => t.name)) + " so far.";
        }
        if(config.offline){
            error.textContent = "The server could not be reached, please try again later.";
        }
        if(config.googleMapsKey){
            startGoogle(config.googleMapsKey);
        }
    });

    function showTyping(){
        $(".typing-box", panel).hidden = false;
    }

    function startGoogle(key){
        loadGoogleMaps(key).then(() => {
            const search = new google.maps.places.PlaceAutocompleteElement({
                includedRegionCodes: ["us"],
                includedPrimaryTypes: ["street_address", "premise", "subpremise"],
                locationRestriction: unionCounty
            });
            search.addEventListener("gmp-select", async event => {
                try{
                    const place = event.placePrediction.toPlace();
                    await place.fetchFields({ fields: ["addressComponents", "location"] });
                    fields.house.value = addressPart(place, "street_number", false);
                    fields.street.value = addressPart(place, "route", true);
                    picked = place.location ? {
                        house: fields.house.value, street: fields.street.value,
                        location: { lat: place.location.lat(), lng: place.location.lng() }
                    } : null;
                    fields.zip.value = addressPart(place, "postal_code", false);
                    const town = addressPart(place, "locality", false) || addressPart(place, "sublocality_level_1", false);
                    const option = Array.from(fields.town.options).find(o => o.textContent === town);
                    if(option){
                        fields.town.value = option.value;
                    }
                    if(!fields.house.value){
                        showTyping();
                        error.textContent = "Pick an address that has a house number, or type the house number in.";
                        return;
                    }
                    form.requestSubmit();
                }
                catch(problem){
                    console.log("error", problem);
                    showTyping();
                    error.textContent = "We could not read that address from Google. Please type it in below.";
                }
            });
            search.addEventListener("gmp-error", () => {
                showTyping();
                $(".search-notice", panel).textContent = "Address search is not available right now. Please type your address in below.";
            });
            $(".google-search", panel).appendChild(search);
            $(".google-box", panel).hidden = false;
            //As on the classic page: the typed boxes are one click away under the search
            $(".typing-box", panel).hidden = true;
        }).catch(problem => {
            console.log("error", problem);
            $(".google-box", panel).hidden = true;
            showTyping();
        });
    }

    $(".show-typing", panel).addEventListener("click", () => {
        showTyping();
        fields.house.focus();
    });
    const cancel = $(".cancel", panel);
    if(cancel){
        cancel.addEventListener("click", () => options.onCancel());
    }

    form.addEventListener("submit", async event => {
        event.preventDefault();
        //Google's location only belongs to the address it came with, not to one typed over it
        const location = picked && picked.house === fields.house.value && picked.street === fields.street.value
            ? picked.location : null;
        error.textContent = "";
        const address = {
            house_number: fields.house.value.trim(),
            street: fields.street.value.trim(),
            town: fields.town.value,
            zip: fields.zip.value.trim()
        };
        if(!address.house_number || !address.street){
            showTyping();
            error.textContent = "Enter your house number and street name.";
            (address.house_number ? fields.street : fields.house).focus();
            return;
        }
        submit.disabled = true;
        submit.textContent = "Looking it up…";
        const answer = await lookUp(address, options.upcoming, location);
        submit.disabled = false;
        submit.textContent = "Show my schedule";
        if(!answer.ok){
            showTyping();
            error.textContent = answer.error;
            return;
        }
        address.townId = answer.data.town.id;
        address.town = answer.data.town.name;
        //"W 7th Ave" when the server worked out the E or W the address left out
        if(answer.data.address && answer.data.address.street){
            address.street = answer.data.address.street;
        }
        if(answer.data.address && answer.data.address.zip){
            address.zip = answer.data.address.zip;
            address.state = answer.data.address.state || "NJ";
        }
        useAddress(address);
        showAddressInHeader();
        options.onSaved(answer.data);
    });
}

//The panel at the top of the page that opens from the address button
let pageState = null;

function toggleAddressPanel(force){
    const panel = $("#address-panel");
    const button = $("#address-button");
    const open = force !== undefined ? force : panel.hidden;
    //Without a saved address the home page keeps the form open
    if(!open && !savedAddress() && pageState.needsAddress){
        panel.scrollIntoView({ block: "start" });
        return;
    }
    panel.hidden = !open;
    //The button opens the form itself only while nothing is saved, otherwise the drop-down
    if(!open || !savedAddresses().length){
        button.setAttribute("aria-expanded", open ? "true" : "false");
    }
    if(open){
        buildAddressForm(panel, {
            title: savedAddress() ? "Add a new address" : "Find your pickup days",
            cancellable: !!savedAddress() || !pageState.needsAddress,
            upcoming: pageState.upcoming,
            onCancel: () => { toggleAddressPanel(false); button.focus(); },
            onSaved: answer => {
                toggleAddressPanel(false);
                pageState.render(answer);
                const focusTarget = $("#next") || $("main");
                focusTarget.setAttribute("tabindex", "-1");
                focusTarget.focus();
            }
        });
        panel.scrollIntoView({ block: "start" });
        const first = $("input:not([hidden]), select", panel);
        if(first && !$(".typing-box", panel).hidden){
            first.focus();
        }
        else{
            $("#address-title", panel).setAttribute("tabindex", "-1");
            $("#address-title", panel).focus();
        }
    }
}

//------------------------------------------------------------------ next pickup card
function binsPhrase(count){
    if(count === 1) return "your bin";
    if(count === 2) return "both bins";
    return "all " + count + " bins";
}

//The date and time in New Jersey right now, whatever time zone the visitor's device is in
function newJerseyNow(){
    const parts = {};
    new Intl.DateTimeFormat("en-CA", {
        timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", hourCycle: "h23"
    }).formatToParts(new Date()).forEach(p => { parts[p.type] = p.value; });
    return { date: parts.year + "-" + parts.month + "-" + parts.day, minutes: Number(parts.hour) * 60 + Number(parts.minute) };
}

function minutesOf(text, fallback){
    const m = /^(\d{1,2}):(\d{2})$/.exec(text || "");
    return m ? Number(m[1]) * 60 + Number(m[2]) : fallback;
}

//"before", "during" or "after" the pickup hours on the pickup day. The hours come from the
//county file (pickup_hours), a town can have its own. If the device's clock does not agree
//with the server on the date, the time is not trusted and "before" is used.
function pickupPhase(pickup, county, townId){
    const town = ((county.towns || {})[townId] || {}).pickup_hours || {};
    const hours = Object.assign({ start: "06:00", end: "08:00" }, county.pickup_hours || {}, town);
    const now = newJerseyNow();
    if(now.date !== pickup.date){
        return "before";
    }
    if(now.minutes < minutesOf(hours.start, 360)) return "before";
    if(now.minutes < minutesOf(hours.end, 480)) return "during";
    return "after";
}

//"Garbage", "Garbage and Paper", "Garbage, Paper and Metal"
function andList(words){
    return words.length < 2 ? words.join("") : words.slice(0, -1).join(", ") + " and " + words[words.length - 1];
}

//After the pickup hours: for each category picked up today, when it comes next. Metal every
//other week does not come back with Thursday's garbage, so each one gets its own date.
function missedLine(pickups, cats){
    const today = pickups[0];
    const next = today.streams.map((s, n) => {
        const later = pickups.slice(1).find(p => p.streams.some(t => t.id === s.id));
        return { name: cats[n].name, date: later ? later.date : null };
    });
    const lead = "Today's " + andList(cats.map(c => c.name)) + " pickup has most likely already come by. ";
    const known = next.filter(n => n.date);
    if(!known.length){
        return lead + "If you missed it, check the calendar for the next one.";
    }
    //All on the same day: say it once
    if(known.length === next.length && known.every(n => n.date === known[0].date)){
        return lead + "If you missed it, no worries: the next one is " + longDate(known[0].date) + ".";
    }
    return lead + "If you missed it, no worries: " + andList(next.map(n =>
        "the next " + n.name + " pickup is " + (n.date ? longDate(n.date) : "on the calendar"))) + ".";
}

function curbLine(daysAway, pickup, count, phase){
    if(daysAway === 0 && phase === "during"){
        return count === 1
            ? "Pickup is happening this morning. If your bin is not out yet, put it out right away. The truck may already have come by."
            : "Pickup is happening this morning. If " + binsPhrase(count) + " are not out yet, put them out right away. The truck may already have come by.";
    }
    if(daysAway === 0){
        return count === 1
            ? "Pickup is today. If your bin is not out yet, put it out now."
            : "Pickup is today. If " + binsPhrase(count) + " are not out yet, put them out now.";
    }
    if(daysAway === 1){
        return "Put " + binsPhrase(count) + " at the curb tonight.";
    }
    const night = DAYS[(toDate(pickup.date).getUTCDay() + 6) % 7];
    return "Put " + binsPhrase(count) + " at the curb the night before, on " + night + ".";
}

//Where today's pickup stands ("before", "during", "after" the pickup hours), or "none" when
//the first pickup in the list is not today
function todayPhase(answer, county){
    const first = answer.upcoming.pickups[0];
    if(!first || daysBetween(answer.today, first.date) !== 0){
        return "none";
    }
    return pickupPhase(first, county, answer.town.id);
}

//Which pickup the green card shows: today's until the pickup hours are over, then the next
//one. If no next one is known, today's stays with the "already come by" note.
function cardIndex(answer, county){
    return todayPhase(answer, county) === "after" && answer.upcoming.pickups.length > 1 ? 1 : 0;
}

function renderNext(el, answer, county){
    const pickups = answer.upcoming.pickups;
    el.hidden = false;
    if(!pickups.length){
        el.innerHTML = '<p class="eyebrow">Next pickup</p>'
            + '<p class="next-message">We found no pickups in the next six months. Please check with your town.</p>'
            + '<p class="place">' + esc(placeLine(answer)) + '</p>';
        return;
    }
    const today = todayPhase(answer, county);
    const index = cardIndex(answer, county);
    const next = pickups[index];
    const away = daysBetween(answer.today, next.date);
    const big = away === 0 ? "Today" : away === 1 ? "Tomorrow" : weekday(next.date);
    const unit = away === 1 ? "day" : "days";
    const cats = next.streams.map(s => category(county, answer.town.id, s.id, s.label));
    //After the pickup hours: a note about today's pickup, kept under the next one
    let missed = "";
    if(today === "after"){
        const todayCats = pickups[0].streams.map(s => category(county, answer.town.id, s.id, s.label));
        missed = '<p class="curb curb-missed">' + icon("clock", 20) + '<span>' + esc(missedLine(pickups, todayCats)) + '</span></p>';
    }
    //The curb advice is for the pickup on the card. If the card still shows today after the
    //hours (no next pickup known), the note says it all
    const curb = index === 0 && today === "after" ? "" :
        '<p class="curb">' + esc(curbLine(away, next, next.streams.length, index === 0 && today !== "none" ? today : "before")) + '</p>';
    el.dataset.phase = today;
    const bins = next.streams.map((s, n) => {
        const c = cats[n];
        return '<li class="bin">'
            + '<span class="bin-icon" style="background:' + c.color + '">' + icon(c.icon, 22) + '</span>'
            + '<span class="bin-text"><span class="bin-name">' + esc(c.name) + '</span>'
            + (c.short ? '<span class="bin-short">' + esc(c.short) + '</span>' : '')
            + (s.moved ? '<span class="bin-moved">Moved</span>' : '')
            + '</span></li>';
    }).join("");
    el.innerHTML =
        '<div class="next-top">'
        + '<div class="next-heading">'
        + '<h2 class="eyebrow" id="next-title">Next pickup</h2>'
        + '<p class="next-day">' + big + '</p>'
        + '<p class="next-date">' + esc(longDate(next.date)) + '</p>'
        + '</div>'
        + '<div class="countdown" role="img" aria-label="' + (away === 0 ? "Today" : "In " + away + " " + unit) + '">'
        + '<span class="countdown-num" aria-hidden="true">' + away + '</span>'
        + '<span class="countdown-unit" aria-hidden="true">' + unit + '</span></div>'
        + '</div>'
        + '<ul class="bins" aria-label="Collected that day">' + bins + '</ul>'
        + curb + missed
        + '<p class="place">' + esc(placeLine(answer)) + '</p>';
}

function renderStatus(el, text, withButton){
    el.hidden = false;
    el.innerHTML = '<p class="next-message">' + esc(text) + '</p>'
        + (withButton ? '<div><button type="button" class="button change-address">Change address</button></div>' : '');
    const button = $(".change-address", el);
    if(button){
        button.addEventListener("click", () => toggleAddressPanel(true));
    }
}

//------------------------------------------------------------------ holiday notice
//until (optional): leave out changes after this date, so the box only covers the pickups on screen
function renderNotices(el, answer, until){
    const notices = answer.upcoming.notices.filter(n => !until || n.date <= until);
    if(!notices.length){
        el.hidden = true;
        el.innerHTML = "";
        return;
    }
    const holiday = notices.some(n => n.holiday);
    el.innerHTML = '<span style="color:var(--warn-icon)">' + icon("alert", 22) + '</span>'
        + '<div class="notice-body"><p class="notice-title">' + (holiday ? "Holiday change" : "Schedule change") + '</p>'
        + notices.map(n => '<p>' + esc(n.message) + '</p>').join("") + '</div>';
    el.hidden = false;
}

//------------------------------------------------------------------ town notes
function renderNotes(el, answer){
    if(!answer.notes.length){
        el.hidden = true;
        return;
    }
    el.innerHTML = '<h2 class="card-title">From your town</h2><ul class="notes-list">'
        + answer.notes.map(n => (answer.important_notes || []).includes(n)
            ? '<li class="note-important"><strong>' + esc(n) + '</strong></li>' : '<li>' + esc(n) + '</li>').join("") + '</ul>';
    el.hidden = false;
}

//------------------------------------------------------------------ coming up list
function pickupTitle(names){
    return names.length === 1 ? names[0] + " only" : names.join(" + ");
}

function pickupRows(pickups, answer, county){
    if(!pickups.length){
        return '<li class="empty-row">No more pickups found. Please check with your town.</li>';
    }
    return pickups.map(p => {
        const cats = p.streams.map(s => category(county, answer.town.id, s.id, s.label));
        const moved = p.streams.some(s => s.moved);
        const d = toDate(p.date);
        return '<li class="pickup-row">'
            + '<div class="pickup-when"><span class="pickup-dow" aria-hidden="true">' + DAYS[d.getUTCDay()].slice(0, 3) + '</span>'
            + '<span class="pickup-dom" aria-hidden="true">' + d.getUTCDate() + '</span>'
            + '<span class="visually-hidden">' + esc(longDate(p.date)) + ': </span></div>'
            + '<div class="pickup-what"><span class="pickup-title">' + esc(pickupTitle(cats.map(c => c.name))) + '</span>'
            + '<span class="tags">' + cats.map(c => '<span class="tag" style="background:' + c.color + '">' + esc(c.name) + '</span>').join("") + '</span></div>'
            + (moved ? '<span class="moved">Moved</span>' : '')
            + '</li>';
    }).join("");
}

//------------------------------------------------------------------ reminder switch
function renderReminder(el){
    const on = store.get(KEYS.reminder) === true;
    el.innerHTML =
        '<div class="remind-row">'
        + '<div class="remind-text"><span class="remind-title" id="remind-title">Remind me</span>'
        + '<span class="small muted" id="remind-when">Night before, 7:00 PM</span></div>'
        + '<button type="button" class="switch" aria-labelledby="remind-title" aria-describedby="remind-when remind-note" aria-pressed="' + on + '">'
        + '<span class="switch-track"><span class="switch-knob"></span></span></button>'
        + '</div>'
        + '<p class="small muted" id="remind-note">Coming soon: this setting is saved on this device, but no alerts are sent yet.</p>';
    const button = $(".switch", el);
    button.addEventListener("click", () => {
        const now = button.getAttribute("aria-pressed") !== "true";
        button.setAttribute("aria-pressed", now ? "true" : "false");
        store.set(KEYS.reminder, now);
        //TODO: real reminders. Saving the choice here does nothing else yet. Sending an email,
        //SMS or push alert at 7 PM the night before needs a server side job, a way to reach the
        //visitor (address/phone/push subscription) and their consent, none of which exist yet.
    });
}

//------------------------------------------------------------------ Which bin search (sample data)
function setupWhichBin(el, townId, options){
    const inputId = "bin-search";
    el.dataset.town = townId || "";
    el.innerHTML =
        '<label for="' + inputId + '">Which bin?</label>'
        + '<div class="search-box">' + icon("search", 20, ' style="color:var(--text-2)"')
        + '<input id="' + inputId + '" type="search" autocomplete="off" placeholder="Try “pizza box” or “battery”" aria-describedby="bin-sample"></div>'
        + '<ul class="which-results" aria-live="polite"></ul>'
        + '<p class="sample-note" id="bin-sample"></p>'
        + (options && options.showAll ? '<div class="which-all"></div>' : '');
    const input = $("input", el);
    const results = $(".which-results", el);

    loadCounty(townId).then(({ county, which }) => {
        const items = which && Array.isArray(which.items) ? which.items : [];
        if(which && which.sample){
            $("#bin-sample", el).textContent = "Sample answers only. They have not been checked with your town yet.";
        }

        function answerFor(item){
            const id = (item.towns && townId && item.towns[townId]) || item.category;
            return category(county, townId, id, null);
        }

        function show(query){
            const q = query.trim().toLowerCase();
            results.innerHTML = "";
            if(q.length < 2){
                return;
            }
            const scored = [];
            items.forEach(item => {
                const names = [item.name].concat(item.aliases || []).map(n => n.toLowerCase());
                let score = 0;
                names.forEach(n => {
                    if(n === q) score = Math.max(score, 3);
                    else if(n.startsWith(q)) score = Math.max(score, 2);
                    else if(n.includes(q) || (n.length > 3 && q.includes(n))) score = Math.max(score, 1);
                });
                if(score) scored.push({ item: item, score: score });
            });
            scored.sort((a, b) => b.score - a.score);
            if(!scored.length){
                results.innerHTML = '<li class="which-none">Not found. Contact your town.</li>';
                return;
            }
            results.innerHTML = scored.slice(0, 3).map(({ item }) => {
                const c = answerFor(item);
                return '<li class="which-result">'
                    + '<span class="bin-icon" style="background:' + c.color + ';color:#FFFFFF">' + icon(c.icon, 20) + '</span>'
                    + '<span class="bin-text"><span class="bin-name">' + esc(item.name) + '</span>'
                    + '<span class="bin-short">Goes in: <b>' + esc(c.name) + '</b>' + (c.short ? ' · ' + esc(c.short) : '') + '</span></span>'
                    + '</li>';
            }).join("");
        }

        input.addEventListener("input", () => show(input.value));
        if(input.value){
            show(input.value);
        }

        const all = $(".which-all", el);
        if(all && items.length){
            all.innerHTML = '<p class="small muted" style="margin-bottom:8px">Sample items:</p><div class="button-row">'
                + items.map((item, n) => '<button type="button" class="button" data-n="' + n + '">' + esc(item.name) + '</button>').join("")
                + '</div>';
            all.addEventListener("click", event => {
                const button = event.target.closest("button[data-n]");
                if(button){
                    input.value = items[Number(button.dataset.n)].name;
                    show(input.value);
                    input.focus();
                }
            });
        }
    });
}

//------------------------------------------------------------------ add to calendar
function eventTitle(pickup, answer, county){
    return "Trash pickup: " + pickup.streams.map(s => category(county, answer.town.id, s.id, s.label).name).join(" + ");
}

function googleCalendarLink(pickup, answer, county){
    const params = new URLSearchParams({
        action: "TEMPLATE",
        text: eventTitle(pickup, answer, county),
        dates: compact(pickup.date) + "/" + compact(nextDay(pickup.date)),
        details: "Put your bins at the curb the night before. " + placeLine(answer) + ". From TrashScheduleNJ."
    });
    return "https://calendar.google.com/calendar/render?" + params.toString();
}

function icsText(text){
    return String(text).replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
}

//Lines longer than 75 bytes are folded, as the iCalendar format asks. Counted in UTF-8
//bytes, so a character like "·" (2 bytes) is never split in half
const utf8 = new TextEncoder();
function icsFold(line){
    const parts = [];
    let part = "";
    let bytes = 0;
    for(const char of line){
        const size = utf8.encode(char).length;
        //75 for the first line; the following ones start with a space
        if(bytes + size > 75){
            parts.push(part);
            part = " ";
            bytes = 1;
        }
        part += char;
        bytes += size;
    }
    parts.push(part);
    return parts.join("\r\n");
}

function buildIcs(pickups, answer, county){
    const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
    const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TrashScheduleNJ//New design//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Trash pickups"];
    pickups.forEach(p => {
        lines.push("BEGIN:VEVENT",
            "UID:" + compact(p.date) + "-" + answer.town.id + "-" + String(answer.zone.id).replace(/[^\w-]/g, "") + "@trashschedulenj",
            "DTSTAMP:" + stamp,
            "DTSTART;VALUE=DATE:" + compact(p.date),
            "DTEND;VALUE=DATE:" + compact(nextDay(p.date)),
            "SUMMARY:" + icsText(eventTitle(p, answer, county)),
            "DESCRIPTION:" + icsText("Put your bins at the curb the night before. " + placeLine(answer)
                + ". Holiday changes can still happen, please check with your town."),
            "TRANSP:TRANSPARENT",
            //7:00 PM the night before an all-day event
            "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + icsText(eventTitle(p, answer, county) + " tomorrow"),
            "TRIGGER:-PT5H", "END:VALARM",
            "END:VEVENT");
    });
    lines.push("END:VCALENDAR");
    return lines.map(icsFold).join("\r\n") + "\r\n";
}

//first: the pickup the "next pickup" card shows (0, or 1 after today's pickup hours)
function renderAddToCalendar(el, answer, county, first){
    const pickups = answer.upcoming.pickups.slice(first || 0);
    el.hidden = false;
    el.innerHTML = '<h2 class="remind-title">Add to your calendar</h2>'
        + '<div class="button-row">'
        + (pickups.length
            ? '<a class="button" target="_blank" rel="noopener" href="' + esc(googleCalendarLink(pickups[0], answer, county)) + '">'
              + 'Google Calendar<span class="visually-hidden"> (next pickup, opens in a new tab)</span>' + icon("external", 16) + '</a>'
            : '')
        + '<button type="button" class="button ics">Apple Calendar' + icon("download", 16) + '</button>'
        + '</div>'
        + '<p class="small muted ics-note">Google Calendar adds the next pickup. Apple Calendar downloads the next 30 pickups as a file that most calendar apps can open.</p>';
    const button = $(".ics", el);
    button.addEventListener("click", async () => {
        const a = savedAddress();
        if(!a){
            return;
        }
        button.disabled = true;
        const result = await lookUp(a, 30);
        button.disabled = false;
        if(!result.ok){
            $(".ics-note", el).textContent = result.error;
            return;
        }
        const blob = new Blob([buildIcs(result.data.upcoming.pickups, result.data, county)], { type: "text/calendar;charset=utf-8" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = "trash-pickups.ics";
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(link.href), 10000);
    });
}

//------------------------------------------------------------------ pages
function addressPanel(){
    const panel = document.createElement("section");
    panel.id = "address-panel";
    panel.className = "card setup o-setup full";
    panel.setAttribute("aria-labelledby", "address-title");
    panel.hidden = true;
    $("main").prepend(panel);
    return panel;
}

async function loadSchedule(upcoming, render, statusEl){
    const a = savedAddress();
    if(!a){
        return;
    }
    if(statusEl){
        renderStatus(statusEl, "Loading your schedule…");
    }
    const answer = await lookUp(a, upcoming);
    if(!answer.ok){
        if(statusEl){
            renderStatus(statusEl, answer.error, !answer.offline);
        }
        return;
    }
    completeAddress(a, answer.data);
    render(answer.data);
}

const pages = {
    home(){
        const next = $("#next");
        //12, not 4: after a missed pickup the card names the next date for each category
        const UPCOMING = 12;
        let shown = null;
        pageState = {
            needsAddress: true,
            upcoming: UPCOMING,
            reload: () => {
                if(!savedAddress()){
                    location.reload();
                    return;
                }
                loadSchedule(UPCOMING, pageState.render, next);
            },
            render: async answer => {
                const { county } = await loadCounty(answer.town.id);
                shown = { answer: answer, county: county };
                draw();
                //Only redraw the search when the town changed, so typed text is kept
                if($("#which").dataset.town !== answer.town.id){
                    setupWhichBin($("#which"), answer.town.id);
                }
            }
        };
        //Draws everything that depends on the time of day. After the pickup hours the card
        //moves on to the next pickup, so the Coming up list starts one later too
        function draw(){
            const { answer, county } = shown;
            const first = cardIndex(answer, county);
            renderNext(next, answer, county);
            const onScreen = answer.upcoming.pickups.slice(0, first + 4);
            renderNotices($("#holiday"), answer, onScreen.length ? onScreen[onScreen.length - 1].date : null);
            renderNotes($("#notes"), answer);
            $("#coming").hidden = false;
            $("#coming-list").innerHTML = pickupRows(answer.upcoming.pickups.slice(first + 1, first + 4), answer, county);
            renderAddToCalendar($("#addcal"), answer, county, first);
        }
        renderReminder($("#remind"));
        //Redraw when 6 or 8 AM passes while the page is open. Nothing is fetched again
        setInterval(() => {
            if(shown && document.visibilityState === "visible"
                && !document.activeElement.closest("#next, #addcal")
                && todayPhase(shown.answer, shown.county) !== next.dataset.phase){
                draw();
            }
        }, 60000);
        const a = savedAddress();
        setupWhichBin($("#which"), a && a.townId);
        if(!a){
            next.hidden = true;
            toggleAddressPanel(true);
            return;
        }
        loadSchedule(UPCOMING, pageState.render, next);
    },

    calendar(){
        const status = $("#calendar-status");
        pageState = {
            needsAddress: true,
            upcoming: 12,
            reload: () => {
                if(!savedAddress()){
                    location.reload();
                    return;
                }
                loadSchedule(12, pageState.render, status);
            },
            render: async answer => {
                const { county } = await loadCounty(answer.town.id);
                status.hidden = true;
                renderNotices($("#holiday"), answer);
                $("#calendar-place").textContent = placeLine(answer);
                $("#coming").hidden = false;
                $("#coming-list").innerHTML = pickupRows(answer.upcoming.pickups, answer, county);
                renderAddToCalendar($("#addcal"), answer, county);
            }
        };
        if(!savedAddress()){
            status.hidden = true;
            toggleAddressPanel(true);
            return;
        }
        loadSchedule(12, pageState.render, status);
    },

    "which-bin"(){
        pageState = {
            needsAddress: false,
            upcoming: 4,
            render: answer => setupWhichBin($("#which"), answer.town.id, { showAll: true }),
            reload: () => {
                const a = savedAddress();
                setupWhichBin($("#which"), a && a.townId, { showAll: true });
            }
        };
        const a = savedAddress();
        setupWhichBin($("#which"), a && a.townId, { showAll: true });
    },

    settings(){
        const list = $("#settings-addresses");
        function showAddresses(){
            const any = savedAddresses().length > 0;
            list.innerHTML = any ? savedListHTML() : '<li class="muted">No address saved yet.</li>';
            $("#forget").hidden = !any;
        }
        pageState = { needsAddress: false, upcoming: 4, render: showAddresses, reload: showAddresses };
        showAddresses();
        renderReminder($("#remind"));
        list.addEventListener("click", event => handleSavedClick(event, (what, address) => {
            showAddresses();
            $("#forget-done").textContent = what === "removed" ? "Removed " + addressLine(address) + "."
                : what === "switched" ? "Now showing " + addressLine(savedAddress()) + "." : "";
        }));
        $("#change-address").addEventListener("click", () => toggleAddressPanel(true));
        $("#forget").addEventListener("click", () => {
            store.remove(KEYS.address);
            store.remove(KEYS.addresses);
            store.remove(KEYS.reminder);
            showAddresses();
            showAddressInHeader();
            renderReminder($("#remind"));
            $("#forget-done").textContent = "Your saved addresses and reminder setting were removed from this device.";
        });
    }
};

//------------------------------------------------------------------ start
(function start(){
    const page = document.body.dataset.page;
    renderChrome(page);
    addressPanel();
    (pages[page] || pages.home)();
})();
