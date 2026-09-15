# Cijeli put — od praznog Raspberry Pi-ja do kontrole preko WordPressa

Ovaj dokument spaja tri odvojena README-a u jedan linearan put, redoslijedom
kojim se stvarno izvodi. Svaka faza kaže **tko** je radi (uloge iz
`tailscale_Readme.md`: ADMIN / INSTALATER / KORISNIK) i **gdje piše puni
detalj** (troubleshooting tablice, sve varijante) ako nešto zapne — ovaj
dokument namjerno ne ponavlja svaku sitnicu iz sve tri datoteke, nego je
karta koja ih povezuje.

| Faza | Što | Tko | Puni detalj |
|---|---|---|---|
| 0 | Priprema slike diska | ADMIN | `tailscale_Readme.md`, Prilog |
| 1 | Fizičko postavljanje uređaja | INSTALATER | `tailscale_Readme.md` DIO 1 |
| 2 | Prvo spajanje (Tailscale + SSH) | ADMIN | `tailscale_Readme.md` DIO 2 |
| 3 | Pokretanje rpictl-a (simulacija) | dev | `README.md` Postavljanje/Pokretanje |
| 4 | Prelazak na pravi hardver | ADMIN | `README.md` Prelazak na Raspberry Pi |
| 5 | Pristup drugim ljudima preko Tailscalea | ADMIN + KORISNIK | `tailscale_Readme.md` DIO 3, `README.md` Daljinski pristup |
| 6 | WordPress bridge — Pi strana | ADMIN | `README.md` Daljinski pristup preko WordPressa |
| 7 | WordPress bridge — WordPress strana | ADMIN | `wordpress-plugin/rpictl-bridge/README.md` |
| 8 | Provjera cijelog lanca | svi | ovaj dokument, dolje |

---

## Faza 0 — Priprema slike diska

**Tko: ADMIN, prije nego se bilo što fizički postavi.**

Slika (`raspios-trixie-arm64-lite.7z` + `.txt` kontrolni broj) je već
pripremljena i sadrži gotovu konfiguraciju (cloud-init `user-data` +
`config.txt`), unaprijed ugrađenu tako da se sve iduće faze mogu odraditi
bez ijedne ručne postavke na samom uređaju:

- ADMIN-ov SSH javni ključ (prijava na Pi bez lozinke)
- jednokratan Tailscale auth key (Pi se sam prijavi na tailnet pri prvom
  paljenju — nema ekrana/browsera za normalnu prijavu)
- `dtparam=i2c_arm=on` (senzor), `dtparam=audio=on` (razglas),
  `gpio=17=op,dl` (ventilator radi kod nepoznatog stanja pina tijekom boota
  — sigurnosni fail-safe, isti princip kao svugdje drugdje u sustavu)
- osnovni paketi, ograničen journald, hardverski watchdog, swap isključen

Ovo se radi jednom po slici, ne po uređaju — više Raspberry Pi-jeva se može
podići s iste slike.

## Faza 1 — Fizičko postavljanje uređaja

**Tko: INSTALATER, na lokaciji. Trajanje: ~40 min.**

1. Provjeri SHA256 checksum `.7z` datoteke prije bilo čega — oštećena
   datoteka zapiše se na karticu bez greške, ali se uređaj neće dignuti.
2. Raspakiraj `.7z` → dobiješ `.img` (~2.8 GB).
3. Raspberry Pi Imager → Choose OS → **Use custom** → odaberi `.img` →
   Choose storage → karticu → Next.
4. **Kritična točka:** na pitanje "Would you like to apply OS customisation
   settings?" odaberi **NO**. Slika već ima sve postavke — ako odabereš da,
   Imager ih pregazi i uređaj se neće moći spojiti.
5. Pusti zapisivanje + Verifying do kraja (10–15 min).
6. Redoslijed spajanja je bitan: kartica u Pi → mrežni kabel u router → **tek
   onda** napajanje.
7. Provjeri lampice (crvena stalno = struja OK, zelena nepravilno trepće =
   čita s kartice). Prvo pokretanje traje 15–20 min i uređaj se sam jednom
   restarta — normalno, ne diraj ga.

## Faza 2 — Prvo spajanje (Tailscale + SSH)

**Tko: ADMIN, sa svog računala, čim INSTALATER javi da je uređaj upaljen.**

Instaliraj Tailscale (`tailscale.com/download`), prijavi se **interaktivno**
kroz browser (to je drugačiji mehanizam od auth key-a kojim se Pi sam
prijavio u Fazi 0/1 — vidi objašnjenje mehanizma u `README.md`, "Kako
Tailscale i SSH zapravo rade iza scene"). Provjeri: `tailscale status`.

Kad se `spremiste` pojavi u `tailscale status` (može potrajati do 20 min od
paljenja):

```bash
ssh ivan@spremiste
```

Prvi put pita o "authenticity of host" — upiši `yes`. Ako ime ne radi, koristi
`100.x.y.z` adresu iz `tailscale status`.

**Odmah nakon prvog spajanja, četiri obavezne radnje:**

1. `passwd` — promijeni privremenu lozinku.
2. Tailscale admin konzola → Machines → `spremiste` → **Disable key expiry**
   (bez ovoga uređaj za ~180 dana tiho ispadne s mreže — nema ekran da se
   sam ponovno potvrdi).
3. Tailscale admin konzola → Settings → Keys → **revoke** auth key iz Faze 0
   (uređaj je sad trajno prepoznat po vlastitom identitetu, ključ više ne
   treba i "putovao je internetom").
4. Provjeri da je instalacija prošla: `ls /var/log/storage-room-provisioned`
   (ako ne postoji: `sudo cat /var/log/cloud-init-output.log`).

Provjera hardvera dok si već unutra:

```bash
i2cdetect -y 1              # senzor na 0x76 ili 0x77
vcgencmd get_throttled      # mora biti throttled=0x0 (inace slabo napajanje)
vcgencmd measure_temp
ip a
timedatectl                 # nema RTC baterije - sat se sinkronizira preko NTP-a
```

## Faza 3 — Pokretanje rpictl-a (simulacija)

**Tko: developer — može biti na desktopu (bilo gdje, i prije nego Faza 0–2
uopće postoje) ili direktno na Pi-ju preko SSH-a iz Faze 2.**

`rpictl` namjerno radi identično na desktopu i na Pi-ju — `simulate: true`
(default u `config.yaml`) znači lažni HAL, bez ijednog komada hardvera:

```bash
conda env create -f environment.yml && conda activate rpictl
# ili bez conde: python -m venv .venv && pip install -r requirements.txt

python -m rpictl
```

Otvori `http://127.0.0.1:8000` — vidiš temperaturu (simuliranu), gumbe za
ventilator, razglas, glazbu. Isprobaj panel "Simulirani kvarovi" (zamrznuto
očitanje, kvar sabirnice, besmislena vrijednost — sve tri moraju završiti s
upaljenim ventilatorom, to je namjerno dosljedan fail-safe).

```bash
pytest          # 29 testova, sve u milisekundama
ruff check .
```

Ovo je faza u kojoj se kod razvija/mijenja — sve izmjene u ovom repou
(glazba, ducking, token auth, WordPress bridge) su nastale i testirane ovdje,
prije nego su ikad dotakle pravi Pi.

## Faza 4 — Prelazak na pravi hardver

**Tko: ADMIN, na Pi-ju (preko SSH-a iz Faze 2), kad je kod iz Faze 3 gotov.**

1. Kod stigne na Pi (git pull, ili scp, vidi `tailscale_Readme.md` DIO 4 za
   svakodnevni radni tok — VS Code Remote-SSH je preporučen alat baš zato
   što hardver postoji samo na uređaju).
2. U `config.yaml`: `simulate: false`, `sim_speed: 1.0`.
3. `pip install gpiozero RPi.GPIO smbus2 bme680`
4. `sudo apt install i2c-tools`, pa provjeri `i2cdetect -y 1` (0x76 ili 0x77).
   I²C je već uključen u slici (`dtparam=i2c_arm=on` u `config.txt`) — ako
   `/dev/i2c-1` postoji, `raspi-config` nije potreban. Ako senzor javi 0x77,
   promijeni `sensor.i2c_address` u `config.yaml` (default je 0x76).
5. `sudo apt install alsa-utils espeak-ng mpv`
6. **Prije nego uključiš `fan_runs_when_energised`**, provjeri multimetrom
   polaritet relejnog modula — active-low/active-high i COM-NC su dvije
   neovisne inverzije, lako se promaše (vidi `hal/relay_gpio.py`).
7. Ako je overlay read-only: `telemetry.db_path` mora pokazivati na zapisiv
   mount (zasebna particija ili USB), inače baza nestane pri prvom rebootu
   bez greške u logu.
8. `rpictl.service` u `/etc/systemd/system/`, pa
   `systemctl enable --now rpictl`.
9. `server.host` ostavi na `127.0.0.1` osim ako netko treba otvoriti web
   sučelje **s drugog uređaja** preko tailneta (`http://spremiste:8000`) —
   tek tad treba `0.0.0.0`, jer takva veza stiže na mrežno sučelje, ne na
   loopback. **WordPress bridge ovo ne treba**: `tailscale funnel`
   prosljeđuje promet lokalnim procesom na istom stroju preko `127.0.0.1`
   (provjereno testom). `0.0.0.0` usput otvara upravljanje ventilacijom i
   razglasom i cijeloj LAN mreži skladišta — ako to ne želiš, veži server na
   tailscale sučelje (`100.x.y.z`) umjesto na `0.0.0.0`.

Od ovog trenutka isti kod koji je radio u simulaciji upravlja pravim
senzorom, pravim relejem, pravim zvučnikom — vidi "Simulacija vs. pravi
hardver" u `README.md` za zašto ostatak koda ne mora znati razliku.

## Faza 5 — Pristup drugim ljudima preko Tailscalea

**Tko: ADMIN + KORISNIK zajedno.**

Dva različita cilja, dva različita nivoa pristupa:

**A) Netko treba SSH (razvoj/administracija)** — puna procedura,
`tailscale_Readme.md` DIO 3, "dvoja vrata":
1. KORISNIK: `ssh-keygen -t ed25519`, pošalje ADMIN-u `id_ed25519.pub`
   (**javni**, ne privatni — ADMIN provjerava da red počinje s
   `ssh-ed25519`, ne s `BEGIN OPENSSH PRIVATE KEY`).
2. ADMIN otvara **Vrata 1** (mreža): `login.tailscale.com` → Machines →
   `spremiste` → Share → pošalje link KORISNIKU.
3. ADMIN otvara **Vrata 2** (pristup): `ssh ivan@spremiste`, pa
   `nano ~/.ssh/authorized_keys`, doda KORISNIKOV javni ključ na novi red,
   spremi.
4. KORISNIK prihvati Share link, `ssh ivan@spremiste` sad radi.

**B) Netko treba samo web sučelje (ventilator/razglas/glazba, bez SSH-a)** —
dovoljna su samo **Vrata 1**: ADMIN Share-a uređaj (korak 2 iznad), KORISNIK
prihvati link i otvara `http://spremiste:8000` u browseru — odmah ima punu
kontrolu, jer web sučelje (dok `server.api_token` nije postavljen) nema
svoja "druga vrata" kao SSH.

Oduzimanje pristupa: `login.tailscale.com` → Machines → `spremiste` →
**Unshare** (mreža) i/ili `nano ~/.ssh/authorized_keys` na uređaju, obriši
red (SSH) — radi odmah, bez restarta.

## Faza 6 — WordPress bridge, Pi strana

**Tko: ADMIN, na Pi-ju. Preduvjet: Faza 4 (pravi hardver) ili barem Faza 3
(rpictl radi, svejedno simulacija ili ne — bridge radi na oba).**

```bash
openssl rand -hex 32        # generiraj token, zapamti ga za Fazu 7
```

U `config.yaml`:
```yaml
server:
  api_token: "<token iz gornje naredbe>"
```

```bash
sudo systemctl restart rpictl
sudo tailscale funnel 8000   # zapamti ispisani URL, npr. https://spremiste.<tailnet>.ts.net
```

Ovo je **treći, potpuno odvojen put pristupa** uz SSH (Faza 5A) i izravni
web pristup preko Share-a (Faza 5B) — ništa od te dvije se ne mijenja ni
gasi. Zašto treba baš Funnel, ne obična Tailscale mreža: WordPress hosting
nije član tvog tailneta (tuđi je server), pa mu privatna cesta ne pomaže —
Funnel je poseban Tailscale način da samo port 8000 postane dostupan i s
javnog interneta, dok SSH ostaje skriven kao i prije.

## Faza 7 — WordPress bridge, WordPress strana

**Tko: ADMIN, s pristupom wp-adminu i FTP-u (FileZilla).**

1. **FTP**: spoji se u FileZilli na hosting, prevuci cijelu mapu
   `wordpress-plugin/rpictl-bridge/` u `wp-content/plugins/` na serveru.
2. **wp-admin → Plugins**: nađi "rpictl Bridge" → **Activate** (automatski
   registrira ulogu `rpictl_operator`, ne treba je ručno praviti).
3. **wp-admin → Settings → rpictl Bridge**: upiši Pi Funnel URL i token iz
   Faze 6 — moraju biti identični onome u `config.yaml`.
4. **wp-admin → Users**: odaberi osobe kojima daješ pristup → Edit → uloga
   **rpictl operator**.
5. **Really Simple Security** (ako je aktivan): provjeri da
   `wp-json/rpictl/v1/*` nije blokiran u firewall/REST API postavkama.
6. Na stranicu/post stavi shortcode `[rpictl_panel]` (u Elementoru: widget
   "Shortcode").

Puni detalji i rješavanje problema (npr. "Spremište trenutno nije
dostupno"): `wordpress-plugin/rpictl-bridge/README.md`.

## Faza 8 — Provjera cijelog lanca, od 0 do 1

Redom, svaka provjerava jednu kariku:

1. **Faza 1–2 (hardver + mreža):** `vcgencmd get_throttled` vraća `0x0`,
   `ssh ivan@spremiste` radi bez lozinke.
2. **Faza 4 (pravi hardver):** `http://spremiste:8000` (na tailnetu) pokazuje
   pravu, ne simuliranu temperaturu; ručno uključi/isključi ventilator i
   provjeri da se stvarno čuje/vrti.
3. **Faza 5 (Tailscale pristup drugima):** KORISNIK bez SSH pristupa, samo
   sa Share linkom, otvara `http://spremiste:8000` i vidi isto što i ADMIN.
4. **Faza 6 (Funnel + token):** s uređaja koji **nije** na tailnetu (npr.
   mobitel na mobilnim podacima):
   ```
   curl https://spremiste.<tailnet>.ts.net/api/status                    -> 401 (bez tokena)
   curl -H "X-Api-Key: <token>" https://spremiste.<tailnet>.ts.net/api/status  -> 200
   ```
5. **Faza 7 (WordPress panel):** prijavljen kao netko **s**
   `rpictl_operator` ulogom → stranica sa shortcodeom pokazuje živi status i
   gumbi rade (vidljivo istovremeno i u Pi-jevom `http://spremiste:8000`
   sučelju); prijavljen kao netko **bez** te uloge (ili odjavljen) → vidi
   samo poruku "Nemaš pristup ovoj kontroli."

Kad sve pet stavki prođe, lanac je kompletan: fizički uređaj → mreža → kod
na Pi-ju → Tailscale pristup → WordPress pristup, svaka karika neovisno
provjerena.
