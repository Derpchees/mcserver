// ============================================================
// Icono de cada servidor (mismo algoritmo que server_icon_pixels)
// ============================================================

const ICON_GRID = 12;
const ICON_BLOCKS = [{"name":"Mycelium","bands":[[3,["#7b6e83","#6a5f75","#85788c","#71667a"]],[9,["#8a5a3b","#7a4e33","#936240"]]]},{"name":"Podzol","bands":[[3,["#7a5a2b","#6b4e24","#866331","#71532a"]],[9,["#8a5a3b","#7a4e33","#936240"]]]},{"name":"Snowy Grass Block","bands":[[3,["#f2f6f6","#e3eaea","#ffffff","#e9efef"]],[9,["#8a5a3b","#7a4e33","#936240"]]]},{"name":"Dirt Path","bands":[[3,["#9c8148","#8b733f","#a88b4f","#937944"]],[9,["#8a5a3b","#7a4e33","#936240"]]]},{"name":"Crimson Nylium","bands":[[3,["#a31f1f","#8e1a1a","#b32525","#961c1c"]],[9,["#6f2b2b","#5e2424","#7a3131"]]]},{"name":"Warped Nylium","bands":[[3,["#2b7f78","#236b65","#33908a","#28746e"]],[9,["#6f2b2b","#5e2424","#7a3131"]]]},{"name":"TNT","bands":[[4,["#c93a2b","#b53325","#d2422f","#bc3628"]],[4,["#e8e2d6","#d8d2c6","#f0ebe0"]],[4,["#c93a2b","#b53325","#d2422f","#bc3628"]]]},{"name":"Bookshelf","bands":[[2,["#a2834f","#8f7343","#ae8e57"]],[8,["#8b2e2e","#2e4a8b","#c9a33c","#6b3f8f"]],[2,["#a2834f","#8f7343","#ae8e57"]]]},{"name":"Oak Log","bands":[[12,["#6b5232","#5a4429","#745a37","#614a2d"]]]},{"name":"Birch Log","bands":[[12,["#d9d6c9","#e9e6da","#3e3a33","#dcd9cc"]]]},{"name":"Stone","bands":[[12,["#7f7f7f","#727272","#8a8a8a"]]]},{"name":"Cobblestone","bands":[[12,["#7a7a7a","#5f5f5f","#8c8c8c","#6a6a6a"]]]},{"name":"Deepslate","bands":[[12,["#4a4a50","#3e3e44","#55555b"]]]},{"name":"Sand","bands":[[12,["#dbcf9f","#d0c493","#e3d8aa"]]]},{"name":"Netherrack","bands":[[12,["#6f2b2b","#5e2424","#7a3131"]]]},{"name":"End Stone","bands":[[12,["#e8edb0","#dce2a3","#f0f4be"]]]},{"name":"Obsidian","bands":[[12,["#1c1426","#140e1c","#251b33"]]]},{"name":"Glowstone","bands":[[12,["#f2c76a","#d9a94f","#fbe39a"]]]},{"name":"Ice","bands":[[12,["#9ec2f7","#8db4ee","#b0cefa"]]]},{"name":"Pumpkin","bands":[[12,["#d9832b","#c27327","#e0912f","#ca7a28"]]]},{"name":"Block of Gold","bands":[[12,["#f9d849","#e8c238","#fce36a"]]]},{"name":"Block of Diamond","bands":[[12,["#5de1d9","#4ccbc3","#7aebe4"]]]},{"name":"Block of Copper","bands":[[12,["#c0694a","#ae5d41","#cb7655"]]]},{"name":"Block of Amethyst","bands":[[12,["#8b5fc4","#7a51b0","#9c70d3"]]]},{"name":"Honey Block","bands":[[12,["#f6b23c","#e8a132","#fbc257"]]]}];


function iconHash(text) {
    let h = 2166136261;

    for (let i = 0; i < text.length; i++) {
        h ^= text.charCodeAt(i);
        h = Math.imul(h, 16777619) >>> 0;
    }

    return h >>> 0;
}


// Bloque real de Minecraft para cada servidor (mismo calculo que el servidor)
function serverIconBlock(slug) {
    return ICON_BLOCKS[iconHash(slug || "server") % ICON_BLOCKS.length];
}


function serverIconPixels(slug) {

    const pixels = [];

    serverIconBlock(slug).bands.forEach(function([rows, colors]) {
        const rgb = colors.map(function(c) {
            return [1, 3, 5].map(function(i) { return parseInt(c.slice(i, i + 2), 16); });
        });

        for (let y = 0; y < rows; y++) {
            for (let x = 0; x < ICON_GRID; x++) {
                pixels.push(rgb[Math.floor(x * rgb.length / ICON_GRID)]);
            }
        }
    });

    return pixels;
}


function serverIconSvg(slug) {

    const pixels = serverIconPixels(slug);
    let rects = "";

    pixels.forEach(function(rgb, i) {
        rects += '<rect x="' + (i % ICON_GRID) + '" y="' + Math.floor(i / ICON_GRID) + '" width="1" height="1" fill="rgb(' + rgb.join(",") + ')"/>';
    });

    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + ICON_GRID + ' ' + ICON_GRID + '" shape-rendering="crispEdges">' + rects + '</svg>';
}


function serverIconUrl(slug) {
    return "data:image/svg+xml," + encodeURIComponent(serverIconSvg(slug));
}


function serverIconEl(slug, className) {
    const img = document.createElement("img");
    img.className = className;
    img.alt = "";
    img.title = serverIconBlock(slug).name;
    img.src = serverIconUrl(slug);
    return img;
}


// Logo del encabezado y de la pestana: el del servidor abierto o el del sistema
const SYSTEM_FAVICON = (document.querySelector('link[rel="icon"]') || {}).href || "";

function setBrandIcon(slug) {

    const logo = document.querySelector(".brand .logo");
    const favicon = document.querySelector('link[rel="icon"]');
    const key = slug || "";

    if (logo.dataset.icon === key) return;
    logo.dataset.icon = key;

    logo.textContent = "";

    if (slug) {
        logo.classList.add("logo-server");
        logo.append(serverIconEl(slug, "logo-img"));
        if (favicon) favicon.href = serverIconUrl(slug);
    } else {
        logo.classList.remove("logo-server");
        logo.append(el("div", "grass"), el("div", "dirt"));
        if (favicon) favicon.href = SYSTEM_FAVICON;
    }
}
