# rpictl Bridge

Mali WordPress plugin koji prijavljenim korisnicima s ulogom `rpictl_operator`
daje kontrolu spremišta (ventilacija, razglas, glazba) preko Raspberry Pi-ja.

Browser nikad ne zove Pi izravno — samo ovaj plugin, server-to-server, preko
`wp_remote_get`/`wp_remote_post`, s tajnim tokenom koji nikad ne napušta
server. Puni kontekst i arhitektura: `WordPress kao ulaznica za punu kontrolu
rpictl-a` plan u glavnom repou, i `README.md`/`tailscale_Readme.md` u
`rpictl` projektu.

**Ovaj plugin ja (Claude) ne mogu instalirati umjesto tebe** — nemam FTP ni
wp-admin pristup. Koraci ispod su za tebe.

## Postavljanje

1. **Generiraj token** na svom računalu (ili bilo gdje):
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

3. **Na Pi-ju**, otvori "drugi ulaz" prema javnom internetu:
   ```
   sudo tailscale funnel 8000
   ```
   Zapamti URL koji ispiše (`https://spremiste.<tailnet>.ts.net`).

4. **FTP (FileZilla)**: spoji se na WordPress hosting (host/user/lozinka od
   hostera), prevuci cijelu ovu mapu `rpictl-bridge/` u `wp-content/plugins/`
   na serveru.

5. **wp-admin → Plugins**: nađi "rpictl Bridge", klikni **Activate**. Ovo
   automatski registrira ulogu `rpictl_operator` (ne treba je ručno praviti).

6. **wp-admin → Settings → rpictl Bridge**: upiši
   - **Pi Funnel URL** — adresa iz koraka 3
   - **API token** — isti string kao u koraku 1/2

7. **wp-admin → Users**: odaberi ljude kojima daješ pristup → **Edit** →
   promijeni ulogu u **rpictl operator**.

   > **Ne mijenjaj ulogu vlastitom administratorskom računu.** Users ekran ima
   > samo jedan izbornik za ulogu, pa bi time prestao biti administrator i
   > izgubio pristup wp-adminu. Nije ni potrebno: aktivacija plugina daje
   > pristup panelu i ulozi administrator.

8. **Really Simple Security** (ako je aktivan) → provjeri pod
   Firewall/REST API postavkama da `wp-json/rpictl/v1/*` nije blokiran; po
   potrebi dodaj iznimku.

9. Na bilo koju stranicu/post stavi shortcode:
   ```
   [rpictl_panel]
   ```
   (u Elementoru: widget "Shortcode", zalijepi isti tekst)

## Provjera da radi

- Prijavljen kao netko **bez** `rpictl_operator` uloge (ili odjavljen) na toj
  stranici → vidi samo poruku "Nemaš pristup ovoj kontroli."
- Prijavljen kao netko **s** ulogom → vidi temperaturu, stanje ventilatora,
  razglas, glazbu, i gumbi stvarno rade (vidljivo i u Pi-jevom vlastitom
  `http://spremiste:8000` sučelju istovremeno).
- Ako panel javlja "Spremište trenutno nije dostupno" → provjeri korak 3
  (je li Funnel još aktivan, `tailscale funnel status` na Pi-ju) i korak 6
  (jesu li URL/token točno upisani, bez razmaka).

## Skidanje pristupa nekome

wp-admin → Users → Edit → makni ulogu `rpictl operator`. Odmah, bez
restarta bilo čega.

## Ako se ikad potpuno makne plugin

Plugins → Delete (ne samo Deactivate) pokreće `uninstall.php`, koji čisti
ulogu i spremljene postavke (URL/token) iz baze.
