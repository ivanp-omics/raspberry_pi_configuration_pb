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
    if (!res.ok) throw new Error(await res.text());
    return res.json();
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

  async function refresh() {
    try {
      render(await call("/status", { method: "GET" }));
    } catch (e) {
      $("rpictl-error").hidden = false;
      $("rpictl-error").textContent = "Spremište trenutno nije dostupno.";
    }
  }

  $("rpictl-fan-buttons").addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    await call("/fan", {
      method: "POST",
      body: JSON.stringify({ mode: b.dataset.mode }),
    });
    refresh();
  });

  $("rpictl-saybtn").addEventListener("click", async () => {
    const input = $("rpictl-saytext");
    const t = input.value.trim();
    if (!t) return;
    await call("/announce", {
      method: "POST",
      body: JSON.stringify({ text: t }),
    });
    input.value = "";
    refresh();
  });

  $("rpictl-music-play").addEventListener("click", async () => {
    await call("/music", {
      method: "POST",
      body: JSON.stringify({ action: "play" }),
    });
    refresh();
  });

  $("rpictl-music-stop").addEventListener("click", async () => {
    await call("/music", {
      method: "POST",
      body: JSON.stringify({ action: "stop" }),
    });
    refresh();
  });

  refresh();
  setInterval(refresh, 5000);
})();
