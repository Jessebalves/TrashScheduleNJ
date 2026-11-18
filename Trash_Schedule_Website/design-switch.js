//The thin dark "Site design: New | Classic" bar at the top of every page, in both designs.
//
//Load it in <head> with:
//   <script src="design-switch.js" data-ui="new" data-home></script>           index.html, the new home and landing page
//   <script src="design-switch.js" data-ui="new"></script>                     other new design pages (at the root)
//   <script src="../design-switch.js" data-ui="classic"></script>              classic pages (classic/)
//
//The choice is saved in localStorage. Only the landing page (index.html) acts on it: a visitor
//who picked Classic is sent on to classic/. Everyone else stays, the new design is the default.
//Everything the bar draws has its own styles, so the classic pages look and work as before
//underneath it.
(function(){
    //What a first-time visitor sees. Change to "classic" to make the classic design the default.
    const DEFAULT_DESIGN = "new";
    const KEY = "tsn.design";

    const script = document.currentScript;
    const current = script.dataset.ui === "new" ? "new" : "classic";
    //The folder of this file is the root of the website
    const root = new URL(".", script.src);
    const homes = { classic: new URL("classic/", root).href, new: root.href };

    function saved(){
        try{
            const value = localStorage.getItem(KEY);
            return value === "new" || value === "classic" ? value : DEFAULT_DESIGN;
        }
        catch(error){
            return DEFAULT_DESIGN;
        }
    }

    //The landing page: go to the visitor's design if it is not this one, keeping any ?query
    //or #part of the address
    if(script.hasAttribute("data-home") && saved() !== current){
        location.replace(homes[saved()] + location.search + location.hash);
        return;
    }

    const css = `
#tsn-design-bar{background:#1B1F1D;color:#FFFFFF;padding:2px 16px;display:flex;flex-wrap:wrap;
  justify-content:flex-end;align-items:center;gap:12px;margin:0;box-sizing:border-box;
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;font-size:13px;line-height:1.2;text-align:left}
#tsn-design-bar .tsn-design-label{font-size:13px;font-weight:500;color:#D5D9D6;margin:0;padding:0}
#tsn-design-bar .tsn-design-group{display:flex;background:#33393A;border-radius:10px;padding:2px;gap:2px}
#tsn-design-bar button{min-height:44px;min-width:44px;margin:0;padding:0 14px;border:none;border-radius:8px;
  font-family:inherit;font-size:13px;font-weight:600;cursor:pointer;background:transparent;color:#FFFFFF;box-shadow:none}
#tsn-design-bar button[aria-pressed="true"]{background:#FFFFFF;color:#1B1F1D}
#tsn-design-bar button:focus-visible{outline:2px solid #FFFFFF;outline-offset:2px}
#tsn-design-bar button[aria-pressed="true"]:focus-visible{outline-color:#8FD3B0}
/* Phones: on the left. 900px is where the new design switches to its desktop layout */
@media (max-width: 899.98px){#tsn-design-bar{justify-content:flex-start}}`;

    function choose(design){
        try{
            localStorage.setItem(KEY, design);
        }
        catch(error){
            //Private windows can refuse storage, the switch still works for this visit
        }
        if(design !== current){
            location.href = homes[design];
        }
    }

    function addBar(){
        const style = document.createElement("style");
        style.textContent = css;
        document.head.appendChild(style);

        const bar = document.createElement("div");
        bar.id = "tsn-design-bar";
        const label = document.createElement("span");
        label.className = "tsn-design-label";
        label.id = "tsn-design-label";
        label.textContent = "Site design:";
        const group = document.createElement("div");
        group.className = "tsn-design-group";
        group.setAttribute("role", "group");
        group.setAttribute("aria-labelledby", "tsn-design-label");
        [["new", "New"], ["classic", "Classic"]].forEach(([design, text]) => {
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = text;
            button.setAttribute("aria-pressed", design === current ? "true" : "false");
            button.addEventListener("click", () => choose(design));
            group.appendChild(button);
        });
        bar.append(label, group);
        document.body.insertBefore(bar, document.body.firstChild);
    }

    if(document.body){
        addBar();
    }
    else{
        document.addEventListener("DOMContentLoaded", addBar);
    }
})();
