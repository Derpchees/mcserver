// ============================================================
// Tema claro / oscuro
// ============================================================

let theme = null;

try {
    const saved = localStorage.getItem("mc-theme");
    if (saved === "light" || saved === "dark") theme = saved;
} catch (error) {
}


function systemTheme() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark";
}


function currentTheme() {
    return theme || systemTheme();
}


function applyTheme() {
    document.documentElement.dataset.theme = currentTheme();
}


const THEME_ICONS = {
    sun: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
    moon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
};


function renderThemeButton() {
    const dark = currentTheme() === "dark";
    const btn = $("themeBtn");
    btn.innerHTML = dark ? THEME_ICONS.sun : THEME_ICONS.moon;
    btn.title = dark ? t("theme.toLight") : t("theme.toDark");
}


function toggleTheme() {

    theme = currentTheme() === "dark" ? "light" : "dark";

    try {
        localStorage.setItem("mc-theme", theme);
    } catch (error) {
    }

    applyTheme();
    renderThemeButton();

    // Las graficas leen colores del tema al dibujarse
    updateStats();
}


if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", function() {
        if (!theme) {
            applyTheme();
            renderThemeButton();
            updateStats();
        }
    });
}


function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}


applyTheme();
