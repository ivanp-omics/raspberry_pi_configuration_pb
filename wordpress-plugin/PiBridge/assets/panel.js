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

  const T_MIN = 0, T_MAX = 50;
  let state = null;

  root.innerHTML = `
    <div class="pibridge-conn" id="pibridge-conn">veza <b>spajanje…</b></div>

    <div class="pibridge-row">
      <h3>Temperatura</h3>
      <div class="pibridge-temp" id="pibridge-temp">--&nbsp;°C</div>
      <div class="pibridge-side">
        <span id="pibridge-hum">vlaga --</span> ·
        <span id="pibridge-age">očitanje --</span>
        <span id="pibridge-pitemp" hidden></span>
      </div>
      <div class="pibridge-track" id="pibridge-track">
        <div class="pibridge-window" id="pibridge-window"></div>
        <div class="pibridge-marker" id="pibridge-marker" style="left:50%"></div>
      </div>
      <div class="pibridge-scale"><span>0 °C</span><span id="pibridge-thresholds">gasi -- / pali --</span><span>50 °C</span></div>
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
      <div class="pibridge-quick" id="pibridge-quick">
        <button type="button" id="pibridge-dingbtn">🔔 Ding dong</button>
        <button type="button" id="pibridge-alarmbtn" class="pibridge-danger">🚨 Alarm</button>
        <button type="button" id="pibridge-recbtn">⏺ Snimi</button>
      </div>
      <div class="pibridge-recrow" id="pibridge-recrow" hidden>
        <span class="pibridge-recdot"></span>
        <span class="pibridge-rectime" id="pibridge-rectime">Snimam… 0:00</span>
        <button type="button" id="pibridge-recstop">■ Stani</button>
      </div>
      <p class="pibridge-alarmline" id="pibridge-alarmline" hidden></p>
      <p class="pibridge-reason" id="pibridge-saystate">Red je prazan.</p>
    </div>

    <div class="pibridge-row">
      <h3>Glazba</h3>
      <div class="pibridge-buttons">
        <button type="button" id="pibridge-music-play">Pusti</button>
        <button type="button" id="pibridge-music-stop">Zaustavi</button>
      </div>

      <div class="pibridge-volrow">
        <label for="pibridge-vol">Glasnoća</label>
        <input type="range" id="pibridge-vol" min="0" max="100" step="1" value="40">
        <span class="pibridge-volval" id="pibridge-volval">40 %</span>
      </div>

      <div class="pibridge-say">
        <select id="pibridge-stationpick">
          <option value="">— odaberi postaju —</option>
        </select>
      </div>
      <div class="pibridge-say">
        <input type="text" id="pibridge-stationurl" placeholder="ili upiši adresu streama">
        <button type="button" id="pibridge-stationplay">Pusti</button>
      </div>

      <p class="pibridge-reason" id="pibridge-musicstate">Zaustavljeno.</p>
    </div>

    <div class="pibridge-row">
      <h3>Slušanje prostorije</h3>
      <div class="pibridge-quick">
        <button type="button" id="pibridge-listenbtn">🎧 Snimi</button>
      </div>
      <div id="pibridge-listenbox"></div>
      <p class="pibridge-reason" id="pibridge-listenstate">Snimi kratak isječak da čuješ što se tamo događa.</p>
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

  function fmtSec(s) {
    const n = Math.max(0, Math.round(s || 0));
    return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
  }

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

    // Temperatura samog Pija; izvan Pi-ja je null pa se redak sakrije.
    const sys = s.system || {};
    const pit = $("pibridge-pitemp");
    if (sys.cpu_temp_c == null) {
      pit.hidden = true;
    } else {
      pit.hidden = false;
      pit.textContent = ` · Pi ${sys.cpu_temp_c.toFixed(0)} °C`;
      pit.className = sys.cpu_temp_c >= (sys.throttle_c ?? 80) ? "pibridge-hot"
                    : sys.cpu_temp_c >= (sys.warn_c ?? 70) ? "pibridge-warm" : "";
    }

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
    $("pibridge-saystate").textContent =
      a.waiting ? "Najava čeka kraj alarma."
      : a.playing ? `Svira: ${a.playing}`
      : (a.pending ? `${a.pending} u redu čekanja.` : "Red je prazan.");

    const m = s.music || {};
    $("pibridge-musicstate").textContent =
      m.status === "playing" ? `Svira: ${m.track}` :
      m.status === "ducked" ? "Pauzirano (najava)" :
      "Zaustavljeno.";

    // Ne diraj klizac dok ga korisnik vuce - inace mu polling otme rucku
    // ispod prsta i vrati je na staru vrijednost.
    if (m.volume != null && !volDirty) {
      $("pibridge-vol").value = m.volume;
      $("pibridge-volval").textContent = m.volume + " %";
    }

    drawStations(s);

    // ---- alarm ----
    const al = s.alarm || {};
    const abtn = $("pibridge-alarmbtn");
    abtn.className = al.active ? "pibridge-on" : "pibridge-danger";
    abtn.textContent = al.active ? "■ ZAUSTAVI ALARM" : "🚨 Alarm";
    const aline = $("pibridge-alarmline");
    aline.hidden = !al.active;
    if (al.active) {
      aline.textContent = `🚨 Alarm svira — automatsko gašenje za ${fmtSec(al.remaining_s)}`;
    }

    // ---- slusanje ----
    const li = s.listen || {};
    const lbtn = $("pibridge-listenbtn");
    if (!listenBusy) {
      lbtn.className = li.recording ? "pibridge-on" : "";
      lbtn.textContent = li.recording ? "■ Zaustavi" : "🎧 Slušaj";
    }
    if (li.recording) {
      const preostalo = Math.max(0, (li.max_seconds || 0) - (li.elapsed_s || 0));
      $("pibridge-listenstate").textContent =
        `● Snima ${fmtSec(li.elapsed_s)} · automatski prekid za ${fmtSec(preostalo)}`;
    }

    $("pibridge-error").hidden = true;
    renderConn(true);
  }

  function drawSpark(rows) {
    const box = $("pibridge-sparkbox");
    if (!rows || rows.length < 2) {
      box.innerHTML = '<p class="pibridge-spark-empty">Još nema dovoljno mjerenja.</p>';
      return;
    }
    // Margine umjesto ravnomjernog razmaka: lijevo za °C natpise, dolje za
    // sate. preserveAspectRatio se makao - rastezanje bi izoblicilo slova.
    const W = 560, H = 150, ML = 36, MR = 10, MT = 10, MB = 24;
    const ts = rows.map(r => r.ts), tv = rows.map(r => r.temperature_c);
    const t0 = Math.min(...ts), t1 = Math.max(...ts);
    const lo = Math.floor(Math.min(...tv) - 0.5);
    const hi = Math.ceil(Math.max(...tv) + 0.5);
    const x = t => ML + (t - t0) / ((t1 - t0) || 1) * (W - ML - MR);
    const y = v => H - MB - (v - lo) / ((hi - lo) || 1) * (H - MT - MB);

    let grid = "", ylab = "";
    const YT = 4;
    for (let i = 0; i <= YT; i++) {
      const v = lo + (hi - lo) * i / YT;
      const yy = y(v).toFixed(1);
      grid += `<line x1="${ML}" y1="${yy}" x2="${W - MR}" y2="${yy}" stroke="#e3e9ec" stroke-width="1"></line>`;
      ylab += `<text x="${ML - 6}" y="${yy}" text-anchor="end" dominant-baseline="middle"
               font-size="10" fill="#5e7079">${v.toFixed(0)}°</text>`;
    }

    let xlab = "";
    const SIX_H = 6 * 3600;
    for (let t = Math.ceil(t0 / SIX_H) * SIX_H; t <= t1; t += SIX_H) {
      const xx = x(t).toFixed(1);
      const sat = new Date(t * 1000).toLocaleTimeString("hr-HR", { hour: "2-digit", minute: "2-digit" });
      xlab += `<line x1="${xx}" y1="${MT}" x2="${xx}" y2="${H - MB}" stroke="#e3e9ec" stroke-width="1"></line>
               <text x="${xx}" y="${H - MB + 14}" text-anchor="middle" font-size="10" fill="#5e7079">${sat}</text>`;
    }

    const th = state && state.climate ? state.climate.thresholds : null;
    const bands = th && th.on_c <= hi && th.off_c >= lo
      ? `<rect x="${ML}" y="${y(th.on_c).toFixed(1)}" width="${W - ML - MR}"
          height="${Math.max(0, (y(th.off_c) - y(th.on_c))).toFixed(1)}"
          fill="rgba(232,133,58,.14)"></rect>` : "";

    const pts = rows.map(r => `${x(r.ts).toFixed(1)},${y(r.temperature_c).toFixed(1)}`).join(" ");

    box.innerHTML = `<svg class="pibridge-spark" viewBox="0 0 ${W} ${H}"
        role="img" aria-label="Temperatura kroz vrijeme">
        ${grid}${xlab}${bands}
        <line x1="${ML}" y1="${MT}" x2="${ML}" y2="${H - MB}" stroke="#c9d3d7"></line>
        <line x1="${ML}" y1="${H - MB}" x2="${W - MR}" y2="${H - MB}" stroke="#c9d3d7"></line>
        ${ylab}
        <polyline points="${pts}" fill="none" stroke="#2f7fb5" stroke-width="2"
          stroke-linejoin="round" stroke-linecap="round"></polyline>
      </svg>
      <div class="pibridge-scale"><span>zadnja 24 h</span><span>${rows.length} mjerenja</span></div>`;
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

  // -- radio postaje (preseti dolaze iz config.yaml na Piju) -------------
  // Izbornik samo popuni polje s adresom; pusta se uvijek ono sto u polju
  // pise, pa se moze i rucno upisati stream koji nije na popisu.

  let stationsDrawn = false;
  function drawStations(s) {
    if (stationsDrawn || !s.stations) return;
    const sel = $("pibridge-stationpick");
    const prazna = document.createElement("option");
    prazna.value = "";
    prazna.textContent = "— odaberi postaju —";
    sel.replaceChildren(prazna, ...s.stations.map(st => {
      const o = document.createElement("option");
      o.value = st.url;
      o.textContent = st.name;
      return o;
    }));
    stationsDrawn = true;
  }

  $("pibridge-stationpick").addEventListener("change", (e) => {
    if (e.target.value) $("pibridge-stationurl").value = e.target.value;
  });

  function playStation() {
    const url = $("pibridge-stationurl").value.trim();
    if (!url) { $("pibridge-stationurl").focus(); return; }
    action(() => call("/music", {
      method: "POST",
      body: JSON.stringify({ action: "play", track: url }),
    }));
  }
  $("pibridge-stationplay").addEventListener("click", playStation);
  $("pibridge-stationurl").addEventListener("keydown", (e) => {
    if (e.key === "Enter") playStation();
  });

  // -- glasnoca glazbe ----------------------------------------------------
  // Salje se na "change" (kad pustis rucku), ne na "input" - inace jedno
  // povlacenje posalje desetke zahtjeva, a svaki drzi PHP radnika.

  let volDirty = false;
  $("pibridge-vol").addEventListener("input", () => {
    volDirty = true;
    $("pibridge-volval").textContent = $("pibridge-vol").value + " %";
  });
  $("pibridge-vol").addEventListener("change", async () => {
    try {
      await call("/music-volume", {
        method: "POST",
        body: JSON.stringify({ volume: Number($("pibridge-vol").value) }),
      });
      await refresh();
    } catch (err) {
      showError(err);
    } finally {
      volDirty = false;
    }
  });

  // -- preset zvuk --------------------------------------------------------

  $("pibridge-dingbtn").addEventListener("click", () => {
    action(() => call("/announce", {
      method: "POST",
      body: JSON.stringify({ file: "dingdong.wav" }),
    }));
  });

  // Alarm nije najava iz reda nego vlastiti servis koji drzi razglas dok
  // svira - zato svoja ruta, a ne /announce.
  $("pibridge-alarmbtn").addEventListener("click", () => {
    const upaljen = state && state.alarm && state.alarm.active;
    action(() => call("/alarm", {
      method: "POST",
      body: JSON.stringify({ action: upaljen ? "stop" : "start" }),
    }));
  });

  // -- snimanje najave ----------------------------------------------------
  // Isti obrazac kao index.html: MediaRecorder ne zna u WAV, pa se nastavak
  // odredi iz stvarnog tipa snimke (Chrome webm, Firefox ogg, Safari mp4).

  let recorder = null, recChunks = [], recTicker = null, recStarted = 0;

  function pickRecMime() {
    if (!window.MediaRecorder) return null;
    for (const m of ["audio/webm", "audio/ogg", "audio/mp4"]) {
      if (MediaRecorder.isTypeSupported(m)) return m;
    }
    return "";
  }
  function extFor(mime) {
    if (mime.includes("webm")) return "webm";
    if (mime.includes("ogg")) return "ogg";
    if (mime.includes("mp4") || mime.includes("m4a")) return "m4a";
    return "webm";
  }
  function recUi(on) {
    $("pibridge-recrow").hidden = !on;
    $("pibridge-quick").hidden = on;
  }

  async function startRec() {
    // navigator.mediaDevices postoji samo u sigurnom kontekstu (HTTPS ili
    // localhost) - bez ove provjere korisnik dobije golo "reading
    // 'getUserMedia' of undefined" i ne zna sto mu je ciniti.
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      $("pibridge-saystate").textContent = location.protocol === "https:"
        ? "Ovaj preglednik ne dopušta pristup mikrofonu."
        : "Snimanje traži HTTPS — otvori ovu stranicu preko https://, ne http://.";
      return;
    }
    const mime = pickRecMime();
    if (mime === null) {
      $("pibridge-saystate").textContent = "Ovaj browser ne podržava snimanje (MediaRecorder).";
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      $("pibridge-saystate").textContent = "Nema pristupa mikrofonu: " + err.message;
      return;
    }
    recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    recChunks = [];
    recorder.ondataavailable = (e) => { if (e.data.size) recChunks.push(e.data); };
    recorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      recUi(false);
      clearInterval(recTicker);
      await sendRec(new Blob(recChunks, { type: recorder.mimeType }));
    };
    recorder.start();
    recStarted = Date.now();
    recUi(true);
    recTicker = setInterval(() => {
      const s = Math.floor((Date.now() - recStarted) / 1000);
      $("pibridge-rectime").textContent =
        `Snimam… ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    }, 250);
  }

  async function sendRec(blob) {
    const ext = extFor(blob.type || "audio/webm");
    $("pibridge-saystate").textContent = "Šaljem snimku…";
    try {
      const res = await fetch(`${cfg.restUrl}/announce-clip?ext=${ext}`, {
        method: "POST",
        headers: {
          "X-WP-Nonce": cfg.nonce,
          "Content-Type": blob.type || "application/octet-stream",
        },
        body: blob,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error((body && body.message) || "Snimka nije poslana.");
      }
      $("pibridge-saystate").textContent = "Snimka poslana na razglas.";
      await refresh();
    } catch (err) {
      $("pibridge-saystate").textContent = "Snimka nije poslana: " + err.message;
    }
  }

  $("pibridge-recbtn").addEventListener("click", startRec);
  $("pibridge-recstop").addEventListener("click", () => {
    if (recorder && recorder.state !== "inactive") recorder.stop();
  });

  // -- slusanje prostorije ------------------------------------------------
  // Audio dolazi kao base64 u JSON-u (vidi pibridge_audio_request u PHP-u),
  // pa se ovdje pretvara natrag u Blob za <audio> element.

  // Prekidac: start otvara sesiju na Piju, stop je zatvara i vraca snimku
  // (kao base64 u JSON-u, vidi pibridge_audio_request u PHP-u).
  let listenUrl = null;
  let listenBusy = false;

  $("pibridge-listenbtn").addEventListener("click", async () => {
    if (listenBusy) return;
    const btn = $("pibridge-listenbtn");
    const snima = state && state.listen && state.listen.recording;
    listenBusy = true;
    btn.disabled = true;
    try {
      if (!snima) {
        await call("/listen-start", { method: "POST" });
        $("pibridge-listenstate").textContent = "Snimanje u tijeku…";
        await refresh();
      } else {
        $("pibridge-listenstate").textContent = "Zatvaram snimku…";
        const out = await call("/listen-stop", { method: "POST" });
        const bin = Uint8Array.from(atob(out.audio_base64), ch => ch.charCodeAt(0));
        if (listenUrl) URL.revokeObjectURL(listenUrl);
        listenUrl = URL.createObjectURL(new Blob([bin], { type: out.mime }));
        const audio = document.createElement("audio");
        audio.controls = true;
        audio.src = listenUrl;
        $("pibridge-listenbox").replaceChildren(audio);
        $("pibridge-listenstate").textContent =
          "Snimljeno " + new Date().toLocaleTimeString("hr-HR");
        audio.play().catch(() => {});
        await refresh();
      }
    } catch (err) {
      $("pibridge-listenstate").textContent = "Slušanje nije uspjelo: " + err.message;
      refresh().catch(() => {});
    } finally {
      listenBusy = false;
      btn.disabled = false;
    }
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

  // Dok alarm ili slusanje traju, odbrojavanje mora teci - 5 s je predugo da
  // bi brojka bila korisna. 2 s, ne 1 s kao na index.html: svaki poziv ovdje
  // drzi PHP radnika, a sesija je ionako omedena na 60 s.
  const BUSY_DELAY = 2000;

  async function tick() {
    if (document.hidden) { schedule(MIN_DELAY); return; }
    await refresh().catch(() => {});
    const traje = state && (
      (state.alarm && state.alarm.active) || (state.listen && state.listen.recording)
    );
    schedule(traje ? BUSY_DELAY : undefined);
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
