// ============================================================
// Utilidades
// ============================================================

function formatBytes(bytes, decimals) {

    if (bytes === null || bytes === undefined) return "-";

    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    let value = Number(bytes);

    while (value >= 1024 && i < units.length - 1) {
        value /= 1024;
        i++;
    }

    const d = decimals !== undefined ? decimals : (value < 10 && i > 0 ? 1 : 0);
    return value.toFixed(d) + " " + units[i];
}


function formatDuration(seconds) {

    const d = Math.floor(seconds / 86400);
    const h = Math.floor(seconds % 86400 / 3600);
    const m = Math.floor(seconds % 3600 / 60);

    if (d > 0) return d + " d " + h + " h";
    if (h > 0) return h + " h " + m + " min";
    return m + " min";
}


function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}


const ICONS = {
    folder: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
    file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/></svg>',
    text: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/></svg>',
    archive: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4"/></svg>',
    edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8l6 6v2"/><path d="M14 3v6h6"/><path d="M18.4 13.6a1.7 1.7 0 0 1 2.4 2.4L15.5 21.3l-3.2.8.8-3.2z"/></svg>',
    download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v12M6 10l6 6 6-6M4 20h16"/></svg>',
    rename: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>',
    copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
    message: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 21l1.9-5.4A8 8 0 1 1 21 12z"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6"/></svg>'
};


function iconButton(icon, title, onClick, danger) {
    const btn = el("button", "icon-btn" + (danger ? " danger" : ""));
    btn.innerHTML = ICONS[icon];
    btn.title = title;
    btn.onclick = function(event) {
        event.stopPropagation();
        onClick();
    };
    return btn;
}


// Cara y skin de un jugador: el panel da la del mod de skins del servidor
// (la que se ve en el juego) o manda a mc-heads.net (la de Mojang)
function playerHeadUrl(name, size, serverId) {
    return "/s/" + (serverId || currentServer) + "/head?name=" + encodeURIComponent(name) + "&size=" + size;
}


function playerSkinUrl(name) {
    return "/s/" + currentServer + "/skin?name=" + encodeURIComponent(name);
}
