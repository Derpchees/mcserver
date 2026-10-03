// ============================================================
// Chat del servidor
// ============================================================

let chatKey = "";
let chatTotal = null;
let chatUnread = 0;


function showPane(name) {

    consolePane = name;
    $("panes").dataset.pane = name;

    document.querySelectorAll(".tab-btn[data-pane]").forEach(function(btn) {
        btn.classList.toggle("active", btn.dataset.pane === name);
    });

    if (name === "chat") {
        chatUnread = 0;
        renderChatBadge();
    }

    const box = $(name);
    box.scrollTop = box.scrollHeight;
}


function renderChatBadge() {
    const badge = $("chatBadge");
    badge.hidden = chatUnread <= 0;
    badge.textContent = chatUnread > 99 ? "99+" : String(chatUnread);
}


function chatTime(ts) {
    return new Date(ts * 1000).toLocaleTimeString(locale(), {
        hour: "2-digit",
        minute: "2-digit"
    });
}


function chatDay(ts) {

    const d = new Date(ts * 1000);
    const today = new Date();
    const yesterday = new Date(Date.now() - 86400000);

    if (d.toDateString() === today.toDateString()) return t("act.today");
    if (d.toDateString() === yesterday.toDateString()) return t("chat.yesterday");

    return d.toLocaleDateString(locale(), {
        weekday: "long",
        day: "numeric",
        month: "long"
    });
}


function chatAvatar(name) {

    const avatar = el("span", "avatar chat-avatar", name.charAt(0).toUpperCase());
    const img = document.createElement("img");
    img.alt = "";
    img.src = "https://mc-heads.net/avatar/" + encodeURIComponent(name) + "/32";
    img.onerror = function() { img.remove(); };
    avatar.append(img);

    return avatar;
}


function chatRow(message) {

    const time = el("span", "chat-time", chatTime(message.ts));
    time.title = new Date(message.ts * 1000).toLocaleString(locale());

    if (message.type === "chat" || message.type === "say") {

        const roleClass = message.type === "say" ? " chat-say chat-role-" + (message.role || "server") : "";
        const row = el("div", "chat-msg" + roleClass);
        const body = el("div", "chat-body");

        const sayName = !message.role || message.role === "server" ? t("chat.server")
            : message.role === "guest" ? t("chat.guest") : message.name;
        const name = el("span", "chat-name", message.type === "say" ? sayName : message.name);

        body.append(name, el("span", "chat-text", message.text));

        const avatar = message.type !== "say" ? chatAvatar(message.name)
            : message.role === "user" ? el("span", "avatar chat-avatar user", (message.name || "?").charAt(0).toUpperCase())
            : message.role === "guest" ? el("span", "avatar chat-avatar guest", "?")
            : el("span", "avatar chat-avatar server", "S");

        row.append(time, avatar, body);
        return row;
    }

    const row = el("div", "chat-msg chat-sys chat-" + message.type);
    let text;

    if (message.type === "join") text = t("chat.joined", { name: message.name });
    else if (message.type === "leave") text = t("chat.left", { name: message.name });
    else text = t("chat.advancement", { name: message.name, a: message.text });

    row.append(time, el("span", "chat-dot"), el("span", "chat-text", text));
    return row;
}


async function loadChat() {

    try {

        const response = await fetch("/chat?t=" + Date.now());
        const data = await response.json();
        const messages = data.messages || [];
        const last = messages.length ? messages[messages.length - 1] : null;
        const key = lang + "|" + data.total + "|" + (last ? last.ts : 0);

        // Mensajes nuevos mientras la pestana del chat no esta a la vista
        if (chatTotal !== null && data.total > chatTotal &&
            ((isNarrow() && consolePane !== "chat") || $("tab-panel").hidden)) {
            chatUnread += messages.slice(-(data.total - chatTotal)).filter(function(m) {
                return m.type === "chat" || m.type === "say";
            }).length;
            renderChatBadge();
        }

        chatTotal = data.total;

        if (key === chatKey) return;
        chatKey = key;

        const box = $("chat");
        const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 60;

        box.textContent = "";

        $("chatSince").textContent = messages.length
            ? t("chat.since", {
                d: new Date(messages[0].ts * 1000).toLocaleDateString(locale(), {
                    day: "numeric", month: "long", year: "numeric"
                })
            })
            : "";

        if (!messages.length) {
            box.append(el("div", "chat-empty", t("chat.empty")));
            return;
        }

        const frag = document.createDocumentFragment();
        let lastDay = "";

        messages.forEach(function(message) {

            const day = new Date(message.ts * 1000).toDateString();

            if (day !== lastDay) {
                frag.append(el("div", "chat-day", chatDay(message.ts)));
                lastDay = day;
            }

            frag.append(chatRow(message));
        });

        box.append(frag);

        if (atBottom || box.dataset.scrolled !== "1") {
            box.scrollTop = box.scrollHeight;
        }

    } catch (error) {
    }
}


$("chat").addEventListener("scroll", function() {
    // Si el usuario sube a leer, no se le mueve al llegar mensajes
    this.dataset.scrolled =
        this.scrollHeight - this.scrollTop - this.clientHeight > 60 ? "1" : "0";
});


async function sendChat() {

    const input = $("chatInput");
    const text = input.value.trim();

    if (!text) return;

    try {

        const response = await fetch("/chat/send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: text })
        });

        const data = await response.json();

        if (data.ok) {
            input.value = "";
            $("chat").dataset.scrolled = "0";
            setTimeout(loadChat, 700);
        } else {
            showToast(serverText(data.message), "red");
        }

    } catch (error) {
        showToast(t("console.sendError"), "red");
    }
}


setInterval(loadChat, 4000);
loadChat();
