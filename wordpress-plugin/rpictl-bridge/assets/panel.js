/* rpictl Bridge - panel u WordPress stranici.
 *
 * Skeleton HTML se gradi jednom, render() nakon toga samo mijenja tekst
 * pojedinih elemenata - da polling svakih par sekundi ne obriše ono sto
 * korisnik tipka u polje za najavu.
 */
(function () {
  const cfg = window.rpictlBridge;
  const root = document.getElementById("rpictl-panel");
  if (!cfg || !root) return;

  root.innerHTML = `
    <div class="rpictl-row">
      <strong>Temperatura:</strong> <span id="rpictl-temp">--</span>
    </div>
    <div class="rpictl-row">
      <strong>Ventilator:</strong> <span id="rpictl-fan">--</span>
      <div class="rpictl-buttons" id="rpictl-fan-buttons">
        <button type="button" data-mode="auto">Automatski</button>
        <button type="button" data-mode="on">Uključi</button>
        <button type="button" data-mode="off">Isključi</button>
      </div>
    </div>
    <div class="rpictl-row">
      <strong>Razglas:</strong> <span id="rpictl-announce">--</span>
      <div class="rpictl-say">
        <input type="text" id="rpictl-saytext" placeholder="Tekst najave">
        <button type="button" id="rpictl-saybtn">Najavi</button>
      </div>
    </div>
    <div class="rpictl-row">
      <strong>Glazba:</strong> <span id="rpictl-music">--</span>
      <div class="rpictl-buttons">
        <button type="button" id="rpictl-music-play">Pusti</button>
        <button type="button" id="rpictl-music-stop">Zaustavi</button>
      </div>
    </div>
    <p class="rpictl-error" id="rpictl-error" hidden></p>
  `;

  const $ = (id) => document.getElementById(id);

  async function call(path, options) {
    const opts = Object.assign(
      { headers: { "X-WP-Nonce": cfg.nonce } },
      options
    );
    if (opts.body) {
      opts.headers["Content-Type"] = "application/json";
    }
    const res = await fetch(cfg.restUrl + path, opts);
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      const err = new Error((body && body.message) || "Spremište trenutno nije dostupno.");
      err.status = res.status;
      throw err;
    }
    return res.json();
  }

  function showError(e) {
    const el = $("rpictl-error");
    el.hidden = false;
    // Istekao nonce (WordPress ga pusta 12-24 h) inace izgleda kao kvar Pi-ja.
    el.textContent = e.status === 403
      ? "Sesija je istekla — osvježi stranicu (F5)."
      : e.message;
  }

  function render(s) {
    const c = s.climate || {};
    const a = s.announcer || {};
    const m = s.music || {};

    $("rpictl-temp").textContent = c.reading
      ? c.reading.temperature_c.toFixed(1) + " °C"
      : "--";
    $("rpictl-fan").textContent =
      (c.fan_on ? "Radi" : "Ne radi") + " (" + (c.mode || "?") + ")";
    for (const b of $("rpictl-fan-buttons").children) {
      b.disabled = b.dataset.mode === c.mode;
    }

    $("rpictl-announce").textContent = a.playing
      ? "Svira: " + a.playing
      : a.pending
        ? a.pending + " u redu čekanja"
        : "Slobodno";

    $("rpictl-music").textContent =
      m.status === "playing"
        ? "Svira: " + m.track
        : m.status === "ducked"
          ? "Pauzirano (najava)"
          : "Zaustavljeno";

    $("rpictl-error").hidden = true;
  }

  const MIN_DELAY = 5000, MAX_DELAY = 60000;
  let delay = MIN_DELAY;
  let timer = null;

  async function refresh() {
    try {
      render(await call("/status", { method: "GET" }));
      delay = MIN_DELAY;
    } catch (e) {
      showError(e);
      delay = Math.min(delay * 2, MAX_DELAY);
    }
  }

  // Svaki zahtjev zauzme jednog PHP radnika na hostingu dok traje, pa se pri
  // greskama razmak udvostrucuje, a u nevidljivoj kartici se ne salje nista.
  function schedule(ms) {
    clearTimeout(timer);
    timer = setTimeout(tick, ms === undefined ? delay : ms);
  }

  async function tick() {
    if (document.hidden) { schedule(MIN_DELAY); return; }
    await refresh();
    schedule();
  }

  // Klik koji ne uspije mora se vidjeti - inace korisnik ne zna je li naredba
  // uopce stigla do ventilacije.
  async function action(fn) {
    try {
      await fn();
      $("rpictl-error").hidden = true;
      await refresh();
      schedule();
    } catch (e) {
      showError(e);
    }
  }

  $("rpictl-fan-buttons").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    action(() => call("/fan", {
      method: "POST",
      body: JSON.stringify({ mode: b.dataset.mode }),
    }));
  });

  $("rpictl-saybtn").addEventListener("click", () => {
    const input = $("rpictl-saytext");
    const t = input.value.trim();
    if (!t) return;
    action(async () => {
      await call("/announce", {
        method: "POST",
        body: JSON.stringify({ text: t }),
      });
      input.value = "";
    });
  });

  $("rpictl-music-play").addEventListener("click", () => {
    action(() => call("/music", {
      method: "POST",
      body: JSON.stringify({ action: "play" }),
    }));
  });

  $("rpictl-music-stop").addEventListener("click", () => {
    action(() => call("/music", {
      method: "POST",
      body: JSON.stringify({ action: "stop" }),
    }));
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) { delay = MIN_DELAY; schedule(0); }
  });

  refresh().then(() => schedule());
})();
