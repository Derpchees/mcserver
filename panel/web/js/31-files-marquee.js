// ============================================================
// Archivos: seleccionar varios arrastrando un recuadro
// ============================================================
//
// Se empieza en el espacio vacio de la lista (no sobre un archivo, que se
// arrastra para moverlo). Con Ctrl o Shift se suma a lo ya elegido. Un
// clic en el vacio sin arrastrar quita la seleccion.

(function() {

    const area = $("fmArea");
    let drag = null;


    function pageBox(a, b) {
        return {
            left: Math.min(a.x, b.x), top: Math.min(a.y, b.y),
            right: Math.max(a.x, b.x), bottom: Math.max(a.y, b.y)
        };
    }


    function update(event) {

        const point = { x: event.clientX + window.scrollX, y: event.clientY + window.scrollY };
        const box = pageBox(drag.start, point);

        if (!drag.moved && box.right - box.left < 5 && box.bottom - box.top < 5) return;

        if (!drag.moved) {
            drag.moved = true;
            drag.node = el("div", "fm-marquee");
            document.body.append(drag.node);
            document.body.classList.add("fm-selecting");
        }

        Object.assign(drag.node.style, {
            left: box.left + "px", top: box.top + "px",
            width: (box.right - box.left) + "px", height: (box.bottom - box.top) + "px"
        });

        const hits = new Set(drag.base);

        document.querySelectorAll("#fileList [data-name]").forEach(function(node) {
            const r = node.getBoundingClientRect();
            const left = r.left + window.scrollX;
            const top = r.top + window.scrollY;

            if (left < box.right && left + r.width > box.left && top < box.bottom && top + r.height > box.top) {
                hits.add(node.dataset.name);
            }
        });

        fmSelected = hits;
        renderSelection();

        // Cerca del borde de la ventana, la pagina se desplaza sola
        if (event.clientY > window.innerHeight - 40) window.scrollBy(0, 18);
        else if (event.clientY < 40) window.scrollBy(0, -18);
    }


    area.addEventListener("mousedown", function(event) {

        if (event.button !== 0 || FM_TOUCH) return;
        if (event.target.closest("[data-name], #fmHead, button, input, a")) return;

        event.preventDefault();

        drag = {
            start: { x: event.clientX + window.scrollX, y: event.clientY + window.scrollY },
            base: event.ctrlKey || event.metaKey || event.shiftKey ? new Set(fmSelected) : new Set(),
            moved: false,
            node: null
        };
    });


    document.addEventListener("mousemove", function(event) {
        if (drag) update(event);
    });


    document.addEventListener("mouseup", function() {

        if (!drag) return;

        if (drag.node) drag.node.remove();
        document.body.classList.remove("fm-selecting");

        // Clic en el vacio sin arrastrar: se quita la seleccion
        if (!drag.moved && !drag.base.size) clearSelection();

        drag = null;
    });
})();
