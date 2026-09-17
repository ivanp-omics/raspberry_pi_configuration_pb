/* PiBridge - panel u WordPress stranici, imitira rpictl/web/index.html.
 *
 * Skeleton HTML se gradi jednom, render() nakon toga samo mijenja tekst/
 * atribute pojedinih elemenata - da polling svakih par sekundi ne obrise
 * ono sto korisnik tipka u polje za najavu. Nema WebSocketa (PHP/WP hosting
 * nije prikladan za dugotrajne proxy-ane WS veze) - umjesto toga polling
 * s backoffom, isti obrazac kao rpictl-bridge/assets/panel.js.
 */
(function () {
  const cfg = window.pibridgeBridge;
  const root = document.getElementById("pibridge-panel");
  if (!cfg || !root) return;

  const T_MIN = 15, T_MAX = 35;
  let state = null;

  root.innerHTML = `
    <div class="pibridge-conn" id="pibridge-conn">veza <b>spajanje…</b></div>

    <div class="pibridge-row">
      <h3>Temperatura</h3>
      <div class="pibridge-temp" id="pibridge-temp">--&nbsp;°C</div>
      <div class="pibridge-side">
        <span id="pibridge-hum">vlaga --</span> ·
        <span id="pibridge-age">očitanje --</span>
      </div>
      <div class="pibridge-track" id="pibridge-track">
        <div class="pibridge-window" id="pibridge-window"></div>
        <div class="pibridge-marker" id="pibridge-marker" style="left:50%"></div>
      </div>
      <div class="pibridge-scale"><span>15 °C</span><span id="pibridge-thresholds">gasi -- / pali --</span><span>35 °C</span></div>
    </div>

    <div class="pibridge-row">
      <h3>Ventilacija</h3>
      <div class="pibridge-fanrow">
        <span class="pibridge-lamp" id="pibridge-lamp"></span>
        <span id="pibridge-fanstate">nepoznato</span>
      </div>
      <p class="pibridge-reason" id="pibridge-reason">čekam prvo očitanje</p>
      <div class="pibridge-buttons" id="pibridge-fan-buttons">
        <button type="button" data-mode="auto">Automatski</button>
        <button type="button" data-mode="on">Stalno uključen</button>
        <button type="button" data-mode="off">Isključen</button>
      </div>
    </div>

    <div class="pibridge-row">
      <h3>Zadnja 24 sata</h3>
      <div id="pibridge-sparkbox"><p class="pibridge-spark-empty">Još nema dovoljno mjerenja.</p></div>
    </div>

    <div class="pibridge-row">
      <h3>Razglas</h3>
      <div class="pibridge-say">
        <input type="text" id="pibridge-saytext" placeholder="Tekst najave">
        <button type="button" id="pibridge-saybtn">Najavi</button>
      </div>
      <p class="pibridge-reason" id="pibridge-saystate">Red je prazan.</p>
    </div>

    <div class="pibridge-row">
      <h3>Glazba</h3>
      <div class="pibridge-buttons">
        <button type="button" id="pibridge-music-play">Pusti</button>
        <button type="button" id="pibridge-music-stop">Zaustavi</button>
      </div>
      <p class="pibridge-reason" id="pibridge-musicstate">Zaustavljeno.</p>
    </div>

    <div class="pibridge-row">
      <h3>Mreža</h3>
      <ul class="pibridge-hosts" id="pibridge-hosts"><li><span class="pibridge-hname">Skeniranje…</span></li></ul>
    </div>

    <p class="pibridge-error" id="pibridge-error" hidden></p>
  `;

  const $ = (id) => document.getElementById(id);
  const pos = (c) => Math.max(0, Math.min(100, (c - T_MIN) / (T_MAX - T_MIN) * 100));

  // -- mreža -----------------------------------------------------------

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

  function renderConn(ok) {
    const el = $("pibridge-conn");
    if (ok) {
      el.className = "pibridge-conn";
      el.innerHTML = "veza <b>uspostavljena</b>";
    } else {
      el.className = "pibridge-conn down";
      el.innerHTML = "veza <b>prekinuta</b>";
    }
  }

  function showError(e) {
    const el = $("pibridge-error");
    el.hidden = false;
    // Istekao nonce (WordPress ga pusta 12-24 h) inace izgleda kao kvar Pi-ja.
    el.textContent = e.status === 403
      ? "Sesija je istekla — osvježi stranicu (F5)."
      : e.message;
    renderConn(false);
  }

  // -- prikaz ------------------------------------------------------------

  function fmtAge(s) {
    if (s == null) return "očitanje --";
    if (s < 90) return `očitanje prije ${Math.round(s)} s`;
    return `očitanje prije ${Math.round(s / 60)} min`;
  }

  function render(s) {
    state = s;
    const c = s.climate || {};
    const r = c.reading;

    $("pibridge-temp").innerHTML = (r ? r.temperature_c.toFixed(1) : "--") + "&nbsp;°C";
    $("pibridge-hum").textContent = r && r.humidity_pct != null ? `vlaga ${r.humidity_pct.toFixed(0)} %` : "vlaga --";
    $("pibridge-age").textContent = fmtAge(c.reading_age_s);

    if (c.thresholds) {
      const on = c.thresholds.on_c, off = c.thresholds.off_c;
      $("pibridge-window").style.left = pos(off) + "%";
      $("pibridge-window").style.width = (pos(on) - pos(off)) + "%";
      $("pibridge-thresholds").textContent = `gasi ${off.toFixed(0)} / pali ${on.toFixed(0)}`;
    }
    if (r) $("pibridge-marker").style.left = pos(r.temperature_c) + "%";

    $("pibridge-lamp").className = "pibridge-lamp" + (c.fan_on ? " on" : "");
    $("pibridge-fanstate").textContent = c.fan_on ? "Radi" : "Ne radi";
    const reason = $("pibridge-reason");
    reason.textContent = c.reason || "";
    reason.className = "pibridge-reason" + (c.healthy === false ? " bad" : "");

    for (const b of $("pibridge-fan-buttons").children) {
      b.disabled = b.dataset.mode === c.mode;
    }

    const a = s.announcer || {};
    $("pibridge-saystate").textContent = a.playing
      ? `Svira: ${a.playing}`
      : (a.pending ? `${a.pending} u redu čekanja.` : "Red je prazan.");

    const m = s.music || {};
    $("pibridge-musicstate").textContent =
      m.status === "playing" ? `Svira: ${m.track}` :
      m.status === "ducked" ? "Pauzirano (najava)" :
      "Zaustavljeno.";

    $("pibridge-error").hidden = true;
    renderConn(true);
  }

  function drawSpark(rows) {
    const box = $("pibridge-sparkbox");
    if (!rows || rows.length < 2) {
      box.innerHTML = '<p class="pibridge-spark-empty">Još nema dovoljno mjerenja.</p>';
      return;
    }
    const W = 560, H = 100, P = 8;
    const ts = rows.map(r => r.ts), tv = rows.map(r => r.temperature_c);
    const t0 = Math.min(...ts), t1 = Math.max(...ts);
    const lo = Math.min(...tv) - 0.5, hi = Math.max(...tv) + 0.5;
    const x = t => P + (t - t0) / ((t1 - t0) || 1) * (W - 2 * P);
    const y = v => H - P - (v - lo) / ((hi - lo) || 1) * (H - 2 * P);
    const pts = rows.map(r => `${x(r.ts).toFixed(1)},${y(r.temperature_c).toFixed(1)}`).join(" ");

    const th = state && state.climate ? state.climate.thresholds : null;
    const bands = th && th.on_c <= hi && th.off_c >= lo
      ? `<rect x="${P}" y="${y(th.on_c).toFixed(1)}" width="${W - 2 * P}"
          height="${Math.max(0, (y(th.off_c) - y(th.on_c))).toFixed(1)}"
          fill="rgba(232,133,58,.14)"></rect>` : "";

    box.innerHTML = `<svg class="pibridge-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"
        role="img" aria-label="Temperatura kroz vrijeme">
        ${bands}
        <polyline points="${pts}" fill="none" stroke="#2f7fb5" stroke-width="2"
          stroke-linejoin="round" stroke-linecap="round"></polyline>
      </svg>
      <div class="pibridge-scale"><span>${lo.toFixed(1)} °C – ${hi.toFixed(1)} °C</span><span>${rows.length} točaka</span></div>`;
  }

  function drawHosts(d) {
    const ul = $("pibridge-hosts");
    const hosts = (d && d.hosts) || [];
    if (!hosts.length) { ul.innerHTML = '<li><span class="pibridge-hname">Nema uređaja.</span></li>'; return; }
    ul.innerHTML = hosts.map(h => `
      <li class="${h.online ? "" : "pibridge-offline"}">
        <span class="pibridge-dot ${h.online ? "up" : ""}"></span>
        <span class="pibridge-hname">${h.hostname || "nepoznat uređaj"}</span>
        <span class="pibridge-hip">${h.ip}</span>
      </li>`).join("");
  }

  // -- akcije --------------------------------------------------------------

  async function action(fn) {
    try {
      await fn();
      await refresh();
      schedule();
    } catch (e) {
      showError(e);
    }
  }

  $("pibridge-fan-buttons").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    action(() => call("/fan", {
      method: "POST",
      body: JSON.stringify({ mode: b.dataset.mode }),
    }));
  });

  function sendSay() {
    const input = $("pibridge-saytext");
    const t = input.value.trim();
    if (!t) { input.focus(); return; }
    action(async () => {
      await call("/announce", { method: "POST", body: JSON.stringify({ text: t }) });
      input.value = "";
    });
  }
  $("pibridge-saybtn").addEventListener("click", sendSay);
  $("pibridge-saytext").addEventListener("keydown", (e) => { if (e.key === "Enter") sendSay(); });

  $("pibridge-music-play").addEventListener("click", () => {
    action(() => call("/music", { method: "POST", body: JSON.stringify({ action: "play" }) }));
  });
  $("pibridge-music-stop").addEventListener("click", () => {
    action(() => call("/music", { method: "POST", body: JSON.stringify({ action: "stop" }) }));
  });

  // -- polling s backoffom ---------------------------------------------

  const MIN_DELAY = 5000, MAX_DELAY = 60000;
  let delay = MIN_DELAY;
  let timer = null;

  async function refresh() {
    try {
      const [s, h, n] = await Promise.all([
        call("/status", { method: "GET" }),
        call("/history", { method: "GET" }),
        call("/network", { method: "GET" }),
      ]);
      render(s);
      drawSpark(h);
      drawHosts(n);
      delay = MIN_DELAY;
    } catch (e) {
      showError(e);
      delay = Math.min(delay * 2, MAX_DELAY);
      throw e;
    }
  }

  async function tick() {
    if (document.hidden) { schedule(MIN_DELAY); return; }
    await refresh().catch(() => {});
    schedule();
  }

  // Svaki zahtjev zauzme jednog PHP radnika na hostingu dok traje, pa se pri
  // greskama razmak udvostrucuje, a u nevidljivoj kartici se ne salje nista.
  function schedule(ms) {
    clearTimeout(timer);
    timer = setTimeout(tick, ms === undefined ? delay : ms);
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) { delay = MIN_DELAY; schedule(0); }
  });

  tick();
})();
