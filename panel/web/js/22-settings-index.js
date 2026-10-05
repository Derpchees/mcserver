// ============================================================
// Ajustes del servidor: indice de secciones
// ============================================================
//
// Una fila de botones arriba de la pestana con el titulo de cada tarjeta:
// al tocar uno se baja a esa seccion, y se marca la que se esta viendo.
// Se rehace solo cuando cambian las tarjetas (MutationObserver).

let settingsIndexSeen = null;


function settingsIndexCards() {
    return Array.from(document.querySelectorAll("#tab-settings .card")).filter(function(card) {
        return card.querySelector(".card-title");
    });
}


function renderSettingsIndex() {

    const nav = $("settingsIndex");
    const cards = settingsIndexCards();

    nav.textContent = "";
    nav.hidden = cards.length < 3;

    if (settingsIndexSeen) settingsIndexSeen.disconnect();

    cards.forEach(function(card, i) {
        card.id = card.id || "set-sec-" + i;
        card.classList.add("set-section");

        const title = card.querySelector(".card-title").textContent.trim();
        const chip = el("button", "set-chip" + (card.classList.contains("danger-zone") ? " is-danger" : ""), title);
        chip.dataset.target = card.id;
        chip.onclick = function() {
            card.scrollIntoView({ behavior: "smooth", block: "start" });
        };
        nav.append(chip);
    });

    // Marca la seccion que esta a la vista (la mas arriba que se ve)
    if (!("IntersectionObserver" in window)) return;

    settingsIndexSeen = new IntersectionObserver(function() {
        const top = cards.find(function(card) {
            const box = card.getBoundingClientRect();
            return box.bottom > 140 && box.top < window.innerHeight;
        });

        nav.querySelectorAll(".set-chip").forEach(function(chip) {
            const on = !!top && chip.dataset.target === top.id;
            chip.classList.toggle("active", on);
            if (on && nav.scrollWidth > nav.clientWidth) {
                chip.scrollIntoView({ block: "nearest", inline: "nearest" });
            }
        });
    }, { threshold: [0, 0.25, 0.5, 1], rootMargin: "-120px 0px 0px 0px" });

    cards.forEach(function(card) { settingsIndexSeen.observe(card); });
}


(function() {
    let pending = false;
    const watch = new MutationObserver(function() {
        if (pending) return;
        pending = true;
        requestAnimationFrame(function() {
            pending = false;
            renderSettingsIndex();
        });
    });

    ["serverConfig", "settingsGroups"].forEach(function(id) {
        watch.observe($(id), { childList: true });
    });
})();
