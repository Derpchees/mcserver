// ============================================================
// Monitor de recursos
// ============================================================

function renderSpark(box, points, max, color, format) {

    const width = box.clientWidth || 300;
    const height = box.clientHeight || 70;

    box._spark = { points: points, max: max, format: format, color: color };

    if (points.length < 2) {
        box.innerHTML = '<div class="hint" style="padding-top:26px"></div>';
        box.firstChild.textContent = t("res.collecting");
        return;
    }

    const n = points.length;
    const x = function(i) { return (i / (n - 1)) * width; };
    const y = function(v) { return height - 2 - Math.min(1, v / max) * (height - 4); };

    let line = "";
    points.forEach(function(p, i) {
        line += (i ? "L" : "M") + x(i).toFixed(1) + " " + y(p[1]).toFixed(1);
    });

    const area = line + "L" + width + " " + height + "L0 " + height + "Z";
    const id = "g" + box.id;

    box.innerHTML =
        '<svg viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="none">'
        + '<defs><linearGradient id="' + id + '" x1="0" y1="0" x2="0" y2="1">'
        + '<stop offset="0" stop-color="' + color + '" stop-opacity=".28"/>'
        + '<stop offset="1" stop-color="' + color + '" stop-opacity="0"/>'
        + '</linearGradient></defs>'
        + '<line x1="0" x2="' + width + '" y1="' + (height / 2) + '" y2="' + (height / 2) + '" stroke="' + cssVar("--border") + '" stroke-dasharray="3 4"/>'
        + '<line x1="0" x2="' + width + '" y1="' + (height - 0.5) + '" y2="' + (height - 0.5) + '" stroke="' + cssVar("--border-strong") + '"/>'
        + '<path d="' + area + '" fill="url(#' + id + ')"/>'
        + '<path d="' + line + '" fill="none" stroke="' + color + '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        + '<g class="hover" style="display:none">'
        + '<line class="hl" y1="0" y2="' + height + '" stroke="' + cssVar("--dim") + '"/>'
        + '<circle class="hc" r="4" fill="' + color + '" stroke="' + cssVar("--surface-2") + '" stroke-width="2"/>'
        + '</g>'
        + '</svg>';

    if (box._hoverX !== undefined) {
        sparkHover(box, box._hoverX);
    }
}


function sparkHover(box, px) {

    const s = box._spark;
    if (!s || s.points.length < 2) return;

    const width = box.clientWidth;
    const height = box.clientHeight;
    const n = s.points.length;
    const i = Math.max(0, Math.min(n - 1, Math.round(px / width * (n - 1))));
    const point = s.points[i];
    const cx = i / (n - 1) * width;
    const cy = height - 2 - Math.min(1, point[1] / s.max) * (height - 4);

    const group = box.querySelector(".hover");
    if (!group) return;

    group.style.display = "";
    group.querySelector(".hl").setAttribute("x1", cx);
    group.querySelector(".hl").setAttribute("x2", cx);
    group.querySelector(".hc").setAttribute("cx", cx);
    group.querySelector(".hc").setAttribute("cy", cy);

    let tip = box.querySelector(".spark-tip");
    if (!tip) {
        tip = el("div", "spark-tip");
        box.append(tip);
    }

    const ago = Math.max(0, Math.round(Date.now() / 1000 - point[0]));
    tip.innerHTML = "";
    tip.append(el("b", "", s.format(point[1])));
    tip.append(el("span", "", "  " + (ago < 3 ? t("res.now") : t("res.agoSec", { s: ago }))));
    tip.style.left = Math.max(50, Math.min(width - 50, cx)) + "px";
}


["cpuChart", "memChart"].forEach(function(id) {

    const box = $(id);

    box.addEventListener("mousemove", function(event) {
        box._hoverX = event.clientX - box.getBoundingClientRect().left;
        sparkHover(box, box._hoverX);
    });

    box.addEventListener("mouseleave", function() {
        delete box._hoverX;
        const group = box.querySelector(".hover");
        if (group) group.style.display = "none";
        const tip = box.querySelector(".spark-tip");
        if (tip) tip.remove();
    });
});


const PART_COLORS = {
    server: "var(--part-server)",
    backups: "var(--part-backups)",
    docker: "var(--part-docker)",
    swap: "var(--part-swap)",
    system: "var(--part-system)",
    reserved: "var(--part-reserved)"
};


// Parte resaltada por disco; sobrevive a los redibujos cada 2 s
const diskFocus = {};


function setDiskFocus(diskEl, id) {

    diskFocus[diskEl.dataset.disk] = id;
    diskEl.classList.toggle("focus", !!id);

    diskEl.querySelectorAll("[data-part]").forEach(function(node) {
        node.classList.toggle("on", node.dataset.part === id);
    });
}


function renderDisks(disks) {

    const box = $("disks");
    box.textContent = "";

    disks.forEach(function(disk) {

        const wrap = el("div", "disk");
        wrap.dataset.disk = disk.id;

        const head = el("div", "disk-head");
        const title = el("span", "disk-name", t("disk.role." + disk.role));
        title.title = disk.label + " · " + disk.mount;

        if (disk.temp) {
            const dt = disk.temp;
            const hot = dt.current >= dt.high;
            const warm = dt.current >= dt.high - 10;
            const badge = el("span", "disk-temp " + (hot ? "is-red" : warm ? "is-amber" : ""),
                Math.round(dt.current) + " °C" + (hot ? " " + t("disk.hot") : ""));
            badge.title = t("disk.tempTitle", { h: dt.high });
            title.append(badge);
        }

        head.append(
            title,
            el("span", "disk-total",
                t("disk.usedOf", { u: formatBytes(disk.used, 1), t: formatBytes(disk.total, 0) }))
        );

        const stack = el("div", "stack");
        const legend = el("div", "legend");

        const pct = function(size) {
            return size / disk.total * 100;
        };

        const addLegend = function(id, label, size, color, isFree) {

            const row = el("div", "legend-row" + (isFree ? " free" : ""));
            row.dataset.part = id;
            row.title = isFree ? t("disk.freeHint") : t("hint." + id);

            const name = el("span", "legend-name");
            const swatch = el("span", "swatch" + (isFree ? " free" : ""));
            if (color) swatch.style.background = color;
            name.append(swatch, document.createTextNode(label));

            row.append(
                name,
                el("span", "legend-size", size === null ? t("disk.calculating") : formatBytes(size, 1)),
                el("span", "legend-pct", size === null ? "" : pct(size).toFixed(1) + "%")
            );

            row.onmouseenter = function() { setDiskFocus(wrap, id); };
            row.onmouseleave = function() { setDiskFocus(wrap, null); };

            legend.append(row);
        };

        disk.parts.forEach(function(part) {

            const size = part.size;
            const partLabel = t("part." + part.id);
            const color = PART_COLORS[part.id] || "var(--part-system)";

            // Partes vacias (p. ej. reserva en 0%) no se muestran
            if (size !== null && size <= 0) return;

            if (size) {
                const seg = el("span");
                seg.dataset.part = part.id;
                seg.style.width = pct(size) + "%";
                seg.style.background = color;
                seg.title = partLabel + ": " + formatBytes(size, 1) + " (" + pct(size).toFixed(1) + "%)";
                seg.onmouseenter = function() { setDiskFocus(wrap, part.id); };
                seg.onmouseleave = function() { setDiskFocus(wrap, null); };
                stack.append(seg);
            }

            addLegend(part.id, partLabel, size, color, false);
        });

        addLegend("free", t("disk.free"), disk.free, null, true);

        wrap.append(head, stack, legend);
        box.append(wrap);

        if (diskFocus[disk.id]) {
            setDiskFocus(wrap, diskFocus[disk.id]);
        }
    });
}


async function updateStats() {

    if ($("tab-panel").hidden) return;

    try {

        const response = await fetch("/stats?t=" + Date.now());
        const data = await response.json();

        const cpu = data.cpu;
        $("cpuValue").textContent = cpu.percent.toFixed(0) + "%";
        $("cpuSub").innerHTML = "";
        $("cpuSub").append(
            el("div", "", t("res.cores", { n: cpu.cores })),
            // Windows no tiene carga promedio
            el("div", "", cpu.load ? t("res.load", { v: cpu.load[0].toFixed(2) }) : ""),
            // docker stats mide por nucleo (100% = 1 nucleo); se pasa a % del total
            el("div", "", data.container ? t("res.serverUse", { v: (data.container.cpu / cpu.cores).toFixed(0) + "%" }) : "")
        );

        if (cpu.temp) {

            const ct = cpu.temp;
            const tone = ct.current >= ct.crit ? "red" : ct.current >= ct.high ? "amber" : "green";

            $("tempBox").hidden = false;
            $("tempValue").textContent = Math.round(ct.current) + " °C";
            $("tempState").textContent =
                tone === "red" ? t("res.tempCrit") : tone === "amber" ? t("res.tempHigh") : "";
            setTone($("tempBox").querySelector(".value"), tone);
            $("tempBox").title =
                t("res.tempLimits", { h: ct.high, c: ct.crit });
        }

        renderSpark($("cpuChart"), cpu.history, 100, cssVar("--chart-cpu"), function(v) {
            return t("res.cpuTip", { v: v.toFixed(0) });
        });

        const mem = data.memory;
        $("memValue").textContent = (mem.used / mem.total * 100).toFixed(0) + "%";
        $("memSub").innerHTML = "";
        $("memSub").append(
            el("div", "", formatBytes(mem.used, 1) + " / " + formatBytes(mem.total, 1)),
            el("div", "", data.container ? t("res.serverUse", { v: formatBytes(data.container.mem_used, 1) }) : "")
        );

        renderSpark($("memChart"), mem.history, mem.total, cssVar("--chart-mem"), function(v) {
            return formatBytes(v, 1) + " (" + (v / mem.total * 100).toFixed(0) + "%)";
        });

        renderDisks(data.disks);

        $("uptime").textContent =
            data.uptime ? t("res.uptime", { d: formatDuration(data.uptime) }) : "";

    } catch (error) {
    }
}
