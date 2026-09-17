# PiBridge

WordPress plugin koji prijavljenim korisnicima s ulogom `pibridge_operator`
daje kontrolu spremišta preko Raspberry Pi-ja — temperatura, histereza,
ventilacija, razglas, glazba, graf zadnja 24h i popis uređaja na mreži.
Odvojen od starijeg `rpictl-bridge` plugina; namjerno vizualno/funkcionalno
prati `rpictl/web/index.html` mnogo bliže (taj plugin pokriva samo osnove).

Browser nikad ne zove Pi izravno — samo ovaj plugin, server-to-server, preko
`wp_remote_get`/`wp_remote_post`, s tajnim tokenom koji nikad ne napušta
server. Puni kontekst: `readmes/rpictl-pregled.md`/`readmes/postavljanje-uredaja.md`
u `rpictl` projektu.

**Ovaj plugin ja (Claude) ne mogu instalirati umjesto tebe** — nemam FTP ni
wp-admin pristup. Koraci ispod su za tebe.

## Lokalni pregled prije uploada

Prije nego ovo ide na pravi WordPress, izgled i interakcije (gumbi, unos
teksta) mogu se provjeriti potpuno lokalno, bez WordPressa, uz mali Python
dev server (samo standardna biblioteka, ne treba `pip install`):

```
cd wordpress-plugin/PiBridge/dev
python devserver.py
```

pa otvori `http://127.0.0.1:8787/` u browseru. Učitava se isti `panel.js`/
`panel.css` koji ide u plugin.

- **Bez `dev/piconf.yaml`** → prikazuju se izmišljeni (mock) podaci, gumbi
  rade na lažnom stanju u memoriji dev servera.
- **S `dev/piconf.yaml`** → prikazuje se **stvarno stanje s Pija** (dev
  server proxira pozive server-to-server, isti obrazac kao `pibridge.php` —
  browser i dalje nikad ne zove Pi izravno, pa nema CORS problema niti
  potrebe dirati `rpictl` kod). Napravi ga:
  ```
  cd wordpress-plugin/PiBridge/dev
  cp piconf.example.yaml piconf.yaml
  # otvori piconf.yaml, upiši Pi Funnel URL i isti API token kao u koraku 1/2 ispod
  ```
  `piconf.yaml` je u `.gitignore` — nikad se ne commita.

Kad je izgled zadovoljavajuć, tek onda ide upload na WordPress (korak 4 ispod).

## Postavljanje

1. **Generiraj token** na svom računalu (ili bilo gdje), ili ponovno iskoristi
   onaj koji već koristi `rpictl-bridge` / `config.local.yaml` na Piju:
   ```
   openssl rand -hex 32
   ```
   Isti string ide na dva mjesta u koraku 2 i 6 — mora biti identičan.

2. **Na Pi-ju**, preko SSH-a, ručno u `config.local.yaml` (ta linija se ne commita natrag u git):
   ```yaml
   server:
     api_token: "<taj isti string>"
   ```
   Restartaj `rpictl` servis (`sudo systemctl restart rpictl`).

3. **Na Pi-ju**, otvori "drugi ulaz" prema javnom internetu (preskoči ako
   `rpictl-bridge` to već radi na istom uređaju — Funnel je jedan po Piju):
   ```
   sudo tailscale funnel --bg 8000
   ```
   Zapamti URL koji ispiše (`https://spremiste.<tailnet>.ts.net`).

4. **Upload**: ili FTP (FileZilla) — prevuci cijelu ovu mapu `PiBridge/` u
   `wp-content/plugins/` na serveru — ili brže, bez FTP klijenta: zipaj mapu
   `PiBridge/` i u **wp-admin → Plugins → Add New → Upload Plugin** odaberi
   taj zip.

   > **Prije zipanja/FTP-a**, ako postoji `dev/piconf.yaml` (pravi API token),
   > obriši ga ili izostavi cijeli `dev/` folder iz onoga što šalješ — WordPress
   > ga nikad ne učitava niti izvršava (samo `pibridge.php` se pokreće, on ne
   > referencira `dev/` nigdje), pa je jedini rizik nepotrebna kopija tokena
   > koja besposleno sjedi na hostingu.

5. **wp-admin → Plugins**: nađi "PiBridge", klikni **Activate**. Ovo
   automatski registrira ulogu `pibridge_operator` (ne treba je ručno praviti).

6. **wp-admin → Settings → PiBridge**: upiši
   - **Pi Funnel URL** — adresa iz koraka 3
   - **API token** — isti string kao u koraku 1/2

7. **wp-admin → Users**: odaberi ljude kojima daješ pristup → **Edit** →
   promijeni ulogu u **PiBridge operator**.

   > **Ne mijenjaj ulogu vlastitom administratorskom računu.** Users ekran ima
   > samo jedan izbornik za ulogu, pa bi time prestao biti administrator i
   > izgubio pristup wp-adminu. Nije ni potrebno: aktivacija plugina daje
   > pristup panelu i ulozi administrator.

8. **Really Simple Security** (ako je aktivan) → provjeri pod
   Firewall/REST API postavkama da `wp-json/pibridge/v1/*` nije blokiran; po
   potrebi dodaj iznimku.

9. Na bilo koju stranicu/post stavi shortcode:
   ```
   [pibridge_panel]
   ```
   (u Elementoru: widget "Shortcode", zalijepi isti tekst)

## Provjera da radi

- Prijavljen kao netko **bez** `pibridge_operator` uloge (ili odjavljen) na toj
  stranici → vidi samo poruku "Nemaš pristup ovoj kontroli."
- Prijavljen kao netko **s** ulogom → vidi temperaturu, traku histereze,
  stanje ventilatora, graf zadnja 24h, razglas, glazbu, popis uređaja na
  mreži — i gumbi stvarno rade (vidljivo i u Pi-jevom vlastitom
  `http://spremiste:8000` sučelju istovremeno).
- Ako panel javlja "Spremište trenutno nije dostupno" → provjeri korak 3
  (je li Funnel još aktivan, `tailscale funnel status` na Pi-ju) i korak 6
  (jesu li URL/token točno upisani, bez razmaka).

## Razlike prema rpictl/web/index.html (namjerne)

- Nema WebSocketa — panel osvježava podatke pollingom (5–60 s, sporije kad
  je kartica sakrivena), jer PHP/WP hosting nije prikladan za dugotrajne
  proxy-ane WebSocket veze.
- Nema unosa API tokena u samom panelu — token se upisuje jednom u
  **Settings → PiBridge** (korak 6), ne po posjetitelju/browseru.
- Nema panela "Simulirani kvarovi" — to je razvojna/testna značajka za
  `simulate: true`, nije namijenjena produkcijskom WordPress sučelju.

## Skidanje pristupa nekome

wp-admin → Users → Edit → makni ulogu `PiBridge operator`. Odmah, bez
restarta bilo čega.

## Ako se ikad potpuno makne plugin

Plugins → Delete (ne samo Deactivate) pokreće `uninstall.php`, koji čisti
ulogu i spremljene postavke (URL/token) iz baze.
