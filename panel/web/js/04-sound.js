// ============================================================
// Sonido de "servidor en linea"
// ============================================================

let lastStatusTone = null;
let audioCtx = null;
let soundOn = true;

try {
    soundOn = localStorage.getItem("mc-sound") !== "off";
} catch (error) {
}


// El boton vive en el menu de avisos (24-alerts-menu.js)
function renderSoundButton() {
    renderAlertsButton();
}


function getAudio() {

    if (!audioCtx) {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return null;
        audioCtx = new Ctx();
    }

    if (audioCtx.state === "suspended") {
        audioCtx.resume();
    }

    return audioCtx;
}


// Los navegadores solo permiten audio despues de una interaccion;
// el primer clic o tecla en la pagina lo habilita
["pointerdown", "keydown"].forEach(function(type) {
    document.addEventListener(type, function() {
        if (soundOn) getAudio();
    }, { once: true, capture: true });
});


function playChime() {

    if (!soundOn) return;

    const ctx = getAudio();
    if (!ctx || ctx.state !== "running") return;

    const now = ctx.currentTime + 0.02;

    const master = ctx.createGain();
    master.gain.value = 0.16;

    // Eco suave para darle cuerpo
    const delay = ctx.createDelay();
    delay.delayTime.value = 0.19;
    const feedback = ctx.createGain();
    feedback.gain.value = 0.28;
    const tone = ctx.createBiquadFilter();
    tone.type = "lowpass";
    tone.frequency.value = 2600;

    delay.connect(tone);
    tone.connect(feedback);
    feedback.connect(delay);
    tone.connect(master);
    master.connect(ctx.destination);

    // Arpegio de sol mayor: G5, B5, D6
    [783.99, 987.77, 1174.66].forEach(function(freq, i) {

        const start = now + i * 0.12;
        const length = 1.6 - i * 0.2;

        [[freq, 1], [freq * 2, 0.12]].forEach(function([f, level]) {

            const osc = ctx.createOscillator();
            osc.type = "sine";
            osc.frequency.value = f;

            const env = ctx.createGain();
            env.gain.setValueAtTime(0.0001, start);
            env.gain.exponentialRampToValueAtTime(level, start + 0.012);
            env.gain.exponentialRampToValueAtTime(0.0001, start + length);

            osc.connect(env);
            env.connect(master);
            env.connect(delay);

            osc.start(start);
            osc.stop(start + length + 0.05);
        });
    });

    setTimeout(function() {
        master.disconnect();
        delay.disconnect();
        feedback.disconnect();
        tone.disconnect();
    }, 4000);
}
