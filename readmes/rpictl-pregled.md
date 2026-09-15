# rpictl

Upravljanje spremištem: ventilacija, razglas, mjerenje temperature, pregled mreže.

Cijeli sustav se vrti na desktopu bez ijednog komada hardvera. To nije posebna
"verzija za testiranje" — to je isti kod, samo s drugim kabelima. Prelazak na
Raspberry Pi je promjena jedne linije u `config.yaml`.

## Postavljanje

```bash
conda env create -f environment.yml
conda activate rpictl
```

Ili bez conde:

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements-dev.txt
```

`requirements.txt` je namjerno **samo runtime** — to je ono što
`provision-rpictl.sh` instalira na Pi. Za razvoj (pytest, ruff) uzmi
`requirements-dev.txt`, koji povlači i jedno i drugo.

## Pokretanje

```bash
python -m rpictl
```

Otvori <http://127.0.0.1:8000>. `sim_speed: 60` znači da jedna simulirana
minuta traje jednu stvarnu sekundu — cijeli dan vidiš u 24 minute, pa
ventilator kroz nekoliko minuta prijeđe puni ciklus paljenja i gašenja.

```bash
python -m pytest    # 43 testa, sve u milisekundama (bare "pytest" ne nalazi paket rpictl)
ruff check .
```

## Što probati prvo

Simulacija ne vrijedi zato što pokazuje da sustav radi kad sve radi — to znaš i
bez nje. Vrijedi zato što pokazuje što se dogodi kad pukne. U panelu
**Simulirani kvarovi** na dnu stranice:

| Kvar | Što se mora dogoditi |
|---|---|
| Zamrzni očitanje | nakon 5 min razlog postane „očitanje staro…", ventilator se pali |
| Kvar sabirnice | broj grešaka raste, aplikacija ne pada, ventilator se pali |
| Besmislena vrijednost | −40 °C se odbacuje, ventilator se pali |

Sve tri završavaju s upaljenim ventilatorom, jer je to isto stanje u koje sklop
pada kad Pi crkne — relej na COM–NC. Ponašanje je namjerno dosljedno.

Isto probaj i s ručnim načinima: „Stalno uključen" mora nadjačati temperaturu.

## Arhitektura

```
HAL  ->  servisi  ->  API
```

Pravilo koje sve drži: **servis smije zvati HAL, HAL nikad ne zove servis, a
servisi se međusobno ne zovu** — komuniciraju porukama preko `bus.py`.

| Datoteka | Odgovornost |
|---|---|
| `hal/base.py` | protokoli koje hardver mora ispuniti |
| `hal/factory.py` | **jedino** mjesto koje zna je li simulacija ili pravi hardver |
| `hal/sensor_fake.py` | termički model prostorije + ubrizgavanje kvarova |
| `hal/relay_gpio.py` | **jedino** mjesto koje zna za COM–NC inverziju |
| `services/climate.py` | termostat; jedini vlasnik ventilatora |
| `services/announcer.py` | red najava s prioritetima, jedna po jedna |
| `services/music.py` | pozadinska glazba; pauzira/nastavlja oko najava preko busa |
| `services/inventory.py` | pamćenje tko je kad viđen na mreži |
| `services/telemetry.py` | zapis u SQLite, brisanje starog |
| `clock.py` | vrijeme kao ovisnost — zato se 8 h testira u 10 ms |
| `app.py` | HTTP/WebSocket; bez ijednog pravila o temperaturi |

`services/climate.py` je podijeljen na `ThermostatPolicy` (čista sinkrona
odluka, bez I/O) i `ClimateService` (asyncio petlja). Bugovi u ovakvom sustavu
gotovo su uvijek u pravilima, a ne u petlji — zato su pravila testabilna bez
čekanja.

### Simulacija vs. pravi hardver

Postoji jedno jedino mjesto u cijelom projektu gdje se odlučuje koji modul se
zove — `hal/factory.py`, funkcija `build_hal()`. Sve ostalo (servisi, `app.py`)
ne zna niti smije znati je li simulacija ili pravi hardver; dobiju gotov
objekt i rade s njim identično u oba slučaja. Grana ide na `simulate:
true/false` iz `config.yaml`:

```python
def build_hal(cfg: Config, clock: Clock) -> Hal:
    if cfg.simulate:
        # ... lažni moduli
        return Hal(sensor=FakeTemperatureSensor(...), fan=FakeFan(...), ...)

    # ... pravi moduli
    return Hal(sensor=Bme680Sensor(...), fan=GpioRelayFan(...), ...)
```

Parovi koji se zamjenjuju, jedan za drugi, isti "oblik" (isti `Protocol` iz
`hal/base.py`):

| Funkcija | Simulacija (`simulate: true`) | Pravi hardver (`simulate: false`) |
|---|---|---|
| Senzor temperature | `hal/sensor_fake.py` → `FakeTemperatureSensor` (termički model prostorije) | `hal/sensor_bme680.py` → `Bme680Sensor` (pravi I2C senzor) |
| Ventilator | `hal/relay_fake.py` → `FakeFan` (u memoriji) | `hal/relay_gpio.py` → `GpioRelayFan` (pravi GPIO relej) |
| Razglas (najave) | `hal/audio_fake.py` → `FakeAudioPlayer` (samo čeka, ne pušta zvuk) | `hal/audio_alsa.py` → `AlsaAudioPlayer` (`aplay`/`espeak-ng`) |
| Glazba | `hal/music_fake.py` → `FakeMusicPlayer` (samo pamti stanje) | `hal/music_mpv.py` → `MpvMusicPlayer` (pravi `mpv` proces) |
| Mreža | `hal/netscan_fake.py` → `FakeNetworkScanner` | `hal/netscan_arp.py` → `ArpNetworkScanner` |

Zašto ostatak koda ne mora znati razliku: svi parovi zadovoljavaju isti
`Protocol` (npr. `TemperatureSensor` traži samo `async def read() -> Reading`)
— `ClimateService` poziva `sensor.read()` i nema pojma je li iza toga pravi
I2C čip ili matematički model sobe. Zato "cijeli sustav radi na desktopu bez
ijednog komada hardvera" iz uvoda ovog README-a nije pojednostavljenje — to je
doslovno isti kod, mijenja se samo koji objekt `build_hal()` vrati.

## Kako radi

### 1. Slanje obavijesti i glazba

**Razglas (najave)** — `services/announcer.py`. `AnnouncerService.enqueue(text, path, priority)`
stavlja najavu u `asyncio.PriorityQueue`, ključ `(priority, redni_broj)` — manji
broj u `Priority` ide prije (`ALARM=0 < NORMAL=5 < LOW=9`), redni broj čuva
FIFO unutar istog prioriteta. `run()` je consumer petlja koja uzme iduću
najavu, objavi `EV_ANNOUNCE {"state":"playing"}` na bus, odsvira je preko HAL-a,
pa objavi `{"state":"done"}`. Uvijek jedna po jedna — dvije se nikad ne
preklapaju, jer bi na PA horni to zvučalo kao kvar.

Dva različita puta ovisno što pošalješ na `/api/announce`:
- **`text`** → `espeak-ng`, živi sintetizator govora (robotski glas, `-v hr`).
  Ništa se ne sprema, tekst se izgovori u letu.
- **`file`** → `aplay` odsvira gotovu datoteku iz `media/`. `aplay` čita samo
  WAV/raw PCM — **ne mp3**.

**Glazba** — `services/music.py` + `hal/music_mpv.py` (real) / `hal/music_fake.py`
(simulacija). `MusicService.play(track=None)` pokrene dugotrajan `mpv` proces
(`--idle`, upravljan preko JSON-IPC unix socketa) koji pusti ili zadanu
datoteku ili cijelu `media/music/` mapu izmiješano i u petlji. Za razliku od
`aplay`, `mpv` dekodira gotovo sve formate (preko ffmpeg-a), pa mp3 tu radi
bez problema.

**Stišavanje (ducking)**: `MusicService` ima vlastitu `run()` petlju koja se
pretplati na *isti* bus i sluša tuđe `EV_ANNOUNCE` poruke — to je jedini spoj
s razglasom, i ide isključivo preko bus poruka, ne izravnim pozivom (pravilo
arhitekture: servisi se međusobno ne zovu). Kad najava krene i glazba
trenutno svira → `hal.music.pause()`. Kad najava završi i bila je pauzirana
zbog toga → `hal.music.resume()` od iste pozicije. `announcer.py` pritom ne
zna da glazba uopće postoji.

`pause()` na pravom hardveru ne samo utiša mpv nego ga stvarno zaustavi
(pozicija se pamti) — inače bi na jeftinom USB zvučnom izlazu bez PipeWire-a
`aplay`/`espeak-ng` pukli s "device busy" jer mpv i dalje drži uređaj otvoren.

### 2. Temperaturna kontrola

Senzor je `hal/sensor_bme680.py` (pravi hardver, I2C, blokirajuće čitanje
prebačeno u thread da ne zaustavi asyncio petlju) ili `hal/sensor_fake.py`
(simulacija — termički model prostorije sa zatvorenom petljom: vanjska dnevna
sinusoida, sunčev dobitak danju, stvarno hlađenje dok ventilator radi — ne
konstantna vrijednost koja ne testira ništa).

`ClimateService._tick()` svakih `climate.poll_interval_s` sekundi pozove
`sensor.read()` (hvata `SensorError` bez rušenja aplikacije, samo broji
grešku i objavi `EV_FAULT`) i preda očitanje `ThermostatPolicy.decide()`.
Politika prvo provjerava je li očitanje uopće vjerodostojno, **prije** nego
ga usporedi s pragovima:

| Provjera | Uvjet | Ishod |
|---|---|---|
| nema očitanja | `reading is None` | ventilator ON, `healthy=False` |
| zastarjelo | starije od `stale_after_s` | ventilator ON (watchdog), `healthy=False` |
| besmisleno | izvan `[valid_min_c, valid_max_c]` | ventilator ON (odbačeno), `healthy=False` |

Tek kad je očitanje "zdravo" ide na histerezu: `temp_on_c`/`temp_off_c` s
razmakom (histereza sprječava treperenje oko jednog praga) plus
`min_on_s`/`min_off_s` minimalna vremena da relej ne cikla. Sve tri simulirane
greške (panel "Simulirani kvarovi") namjerno završavaju s upaljenim
ventilatorom — isto stanje u koje sklop fizički padne kad Pi ugasi (COM-NC),
pa je ponašanje dosljedno bez obzira je li uzrok softverski ili hardverski.

### 3. Kontrola ventilatora

`ClimateService` je "jedini vlasnik ventilatora" — nijedan drugi servis ne
smije zvati `fan.set()` izravno, sve ide kroz njega.

Ručni način rada: `POST /api/fan {"mode": "auto"|"on"|"off"}` →
`ClimateService.set_mode()`, koji odluku primijeni **odmah** (ne čeka sljedeći
ciklus) da gumb u sučelju smjesta pokaže učinak. U `ON`/`OFF` modu
`ThermostatPolicy.decide()` potpuno ignorira temperaturu — ručni način mora
nadjačati sve, uključujući fail-safe provjere iznad.

Fizička strana, samo na pravom hardveru (`hal/relay_gpio.py`) — jedina
inverzija u cijelom projektu, `_energised_for()`, spaja dva neovisna
svojstva iz `config.yaml`:
- `relay_active_high` — je li relejni modul active-low ili active-high
  (elektronika modula)
- `fan_runs_when_energised` — kod ove instalacije ventilator visi na COM-NC,
  pa radi kad relej **nije** pobuđen (ožičenje)

`close()` namjerno **ne** gasi ventilator na izlazu iz programa — otpuštanjem
releja ventilator se upali, isto fail-safe stanje kao kod zastarjelog
očitanja ili kvara senzora: kad program ili cijeli Pi ne rade, sigurnije je da
ventilator radi nego da stoji. U simulaciji (`hal/relay_fake.py`) postoji i
`stuck_on` zastavica za testiranje zalijepljenog releja.

## API

```
GET  /api/status                  sve u jednom
GET  /api/history?hours=24        mjerenja za graf
GET  /api/network                 uređaji na mreži
GET  /api/health                  200 / 503 — za watchdog
POST /api/fan        {"mode": "auto" | "on" | "off"}
POST /api/announce   {"text": "..."} ili {"file": "zvono.wav"}
POST /api/music      {"action": "play" | "stop", "track": "pjesma.mp3"}   track je opcionalan (bez njega pušta cijeli media/music)
                     track smije biti i URL streama: {"action":"play","track":"https://ice1.somafm.com/groovesalad-128-mp3"}
GET  /api/media/{announce|music}        popis datoteka
POST /api/media/{announce|music}        upload (multipart, polje "file"; announce = samo .wav, max 25 MB)
DEL  /api/media/{announce|music}/{ime}  brisanje
GET  /api/sim/fault               trenutno stanje ubrizganog kvara, samo u simulaciji
POST /api/sim/fault  {"freeze": true}     samo u simulaciji
WS   /ws                          događaji uživo
```

Ako je `server.api_token` postavljen u `config.yaml`, svaka `/api/*` ruta
(osim `/api/health`) traži header `X-Api-Key: <token>`, inače vraća 401.
`/ws` traži isti token kao query parametar (`/ws?token=...`), jer browser na
WebSocket vezu ne može staviti vlastito zaglavlje — bez toga bi `/ws` bio
jedina ruta koja živo stanje daje svakome tko dosegne port. Bez
postavljenog tokena (default) ponašanje je identično kao prije — Tailscale
mreža je jedina brava. Vidi "Daljinski pristup preko WordPressa" niže.

## Prelazak na Raspberry Pi

1. `simulate: false` i `sim_speed: 1.0` u `config.yaml`
2. `sudo apt install python3-gpiozero python3-lgpio python3-smbus2` pa
   `pip install bme680` u venv napravljen s `--system-site-packages`.
   (`RPi.GPIO` na Trixieju više ne radi — gpiozero koristi `lgpio`.)
3. uključi I²C u `raspi-config`, provjeri `i2cdetect -y 1` (0x76 ili 0x77)
4. `sudo apt install alsa-utils espeak-ng mpv`
5. `rpictl.service` u `/etc/systemd/system/`, pa `systemctl enable --now rpictl`
6. Tailscale za pristup izvana

Prije nego uključiš `fan_runs_when_energised`, provjeri multimetrom polaritet
svog relejnog modula. Većina jeftinih opto modula je active-low, ali ne svi, a
kod tebe se na to nadovezuje i COM–NC inverzija. Obje su u konfiguraciji baš
zato što se lako promaše.

**Read-only overlay:** `telemetry.db_path` mora pokazivati na zapisiv mount
(zasebna particija ili USB). Na overlayu baza radi savršeno i nestane pri prvom
rebootu, bez ijedne greške u logu.

**Glazba i najave dijele isti USB izlaz.** `MusicPlayer.pause()` stvarno
zaustavlja mpv (ne samo utiša) da oslobodi ALSA uređaj, jer ga jeftini USB
zvučni adapteri i gola ALSA konfiguracija (bez PipeWire-a, kakva je zadana na
Raspberry Pi OS *Lite*) drže isključivo jednom procesu. Bez toga bi najava
preko `aplay`/`espeak-ng` pucala s "device busy" dok glazba svira. Ako
umjesto Lite koristiš desktop image s PipeWire-om (zadano na Bookworm+), ovo
ionako radi samo od sebe.

## Daljinski pristup i drugi ljudi

Puni postupak postavljanja uređaja, dodavanja ljudi na Tailscale i SSH pristupa
je u **`readmes/postavljanje-uredaja.md`** (uloge ADMIN / INSTALATER / KORISNIK) — ovo je
samo dio koji se nadovezuje na to, specifično za **web sučelje rpictl-a** na
portu 8000 (za razliku od SSH pristupa uređaju, koji je posve odvojena stvar).

### Kako Tailscale i SSH zapravo rade "iza scene"

Ovo dvoje rješava dva **različita** problema i uopće se ne poznaju — vrijedi
razumjeti prije ostatka ove sekcije, jer se svaki korak u `readmes/postavljanje-uredaja.md`
oslanja na ovaj mehanizam bez da ga ponovno objašnjava.

**Tailscale = privatna cesta.** Pi u spremištu sjedi iza običnog routera koji
po defaultu blokira sve dolazne veze — bez Tailscalea, tvoje računalo (u
drugom gradu) nema kako doći do njega. Tailscale instalira pozadinski program
(ikona u system trayu, radi neprestano) koji spoji oba uređaja u jednu
privatnu virtualnu mrežu: svaki dobije stabilnu adresu (`100.x.y.z`) i ime
(`spremiste`), a Tailscale sam "prokopa" put kroz routere/firewalle koji bi
inače blokirali vezu. Ta sposobnost — da sam zna razriješiti ime u pravu
adresu — zove se **MagicDNS**: pozadinski program tvom računalu tiho govori
"kad god netko pita za ime `spremiste`, ja znam odgovor".

**SSH = sama radnja na vratima, kad si već stigao.** SSH je ugrađen u Windows
(radi identično iz PowerShella, cmd-a, ili terminala unutar VS Codea — sva
tri pokreću isti `ssh.exe`) i ne zna ništa o Tailscaleu — treba mu samo ime
ili adresa. Kad upišeš `ssh ivan@spremiste`:
1. `ssh` pita Windows "gdje je `spremiste`?"
2. Windows to prosljeđuje Tailscaleu (jer se on registrirao kao MagicDNS)
3. Tailscale vrati pravu adresu i provede vezu kroz svoj privatni tunel
4. `ssh`, preko te veze, provjeri tvoj privatni ključ (iz `C:\Users\<ti>\.ssh\`)
   protiv javnog ključa u `authorized_keys` na uređaju — poklapa se, pusti te
   unutra bez lozinke

Dakle Tailscale = "kako doći do vrata", SSH = "kako se vrata otključavaju".
Da Tailscale nije pokrenut (ugašena ikona u trayu), `ssh ivan@spremiste` ne
zna što je `spremiste` — točno greška `Could not resolve hostname` iz
tablice u `readmes/postavljanje-uredaja.md`.

**Kako se Pi uopće prvi put pridružio toj mreži** (DIO 1–2 u
`readmes/postavljanje-uredaja.md`): slika diska je unaprijed pripremljena (cloud-init
`user-data`) s ADMIN-ovim SSH javnim ključem i jednokratnim Tailscale auth
key-em već ugrađenima — Pi OS *Lite* nema ekran/browser za normalnu prijavu,
pa se pri prvom paljenju sam, automatski prijavi na tailnet tim auth key-em.
ADMIN se, odvojeno, na svom računalu ranije prijavio normalno (interaktivno,
kroz browser) — to je drugačiji mehanizam od onog kojim se Pi prijavio. Čim
se Pi pridruži, oba uređaja se vide u `tailscale status`, i `ssh ivan@spremiste`
radi. Odmah zatim (Korak 2.3) se auth key **revocira** (više ne treba, jer je
Pi sad trajno prepoznat po vlastitom identitetu) i isključuje se "key expiry"
(inače bi uređaj nakon ~180 dana tiho ispao s mreže, a nema ekran da se sam
ponovno potvrdi).

**Zašto onda WordPress bridge treba Tailscale Funnel, a ne samo obični
Tailscale:** WordPress hosting nije član tvog tailneta (tuđi je server) — pa
mu obična privatna cesta ne pomaže, ne može ući. Funnel je poseban Tailscale
način da **jedna, konkretna stvar** (Pi-jev port 8000) postane dostupna i s
običnog javnog interneta, dok SSH i sve ostalo na Pi-ju ostaje skriveno iza
privatne mreže kao i prije — zato ta dva puta (SSH-only tailnet i WordPress
bridge preko Funnela) rade potpuno neovisno jedan o drugom.

`server.host` u `config.yaml` treba biti `0.0.0.0` (ne `127.0.0.1`) **samo**
ako želiš da netko s drugog uređaja otvori web sučelje izravno preko tailneta
(`http://spremiste:8000`, sekcija "Kako netko dobije pristup" niže) ili preko
obične LAN mreže — takva veza stiže na tailscale/Ethernet mrežno sučelje, ne
na loopback, pa je server vezan na `127.0.0.1` odbija.

Za WordPress bridge (Funnel) ovo **nije potrebno** — `tailscale funnel`
prosljeđuje promet lokalnim procesom na istom stroju preko `127.0.0.1` (isto
kao pri desktop testiranju: default `host: "127.0.0.1"` iz `config.yaml` radi
bez ikakve izmjene). Ako ipak postaviš `0.0.0.0`, to dodatno otvara server i
prema LAN-u (ako je uređaj i na Ethernetu) — ako to ne želiš, veži ga
konkretno na tailscale sučelje (`100.x.y.z`) umjesto na `0.0.0.0`.

**Kako netko dobije pristup:** to je `readmes/postavljanje-uredaja.md` DIO 3, "Vrata 1 —
mreža" — ADMIN na `login.tailscale.com` → Machines → `spremiste` → **Share**,
i pošalje link KORISNIKU. Čim KORISNIK prihvati link svojim Tailscale
računom, u browseru otvara `http://spremiste:8000` (Tailscale MagicDNS
razrješava ime, isto kao `ssh ivan@spremiste`; `100.x.y.z` iz `tailscale
status` radi kao rezerva ako ime ne prođe) i ima **odmah** puni pristup
razglasu, glazbi i ventilaciji.

Bitna razlika od SSH-a: SSH traži i "Vrata 2" (KORISNIKOV javni ključ ručno
dodan u `~/.ssh/authorized_keys` na uređaju, DIO 3 koraci 3.6–3.7) prije nego
itko uđe u shell. Web sučelje rpictl-a na tailnetu tu drugu prepreku **nema**
— dok je `server.api_token` prazan (default), Tailscale mreža je jedina
brava. Znači: čim je netko Share-an na `spremiste` (Vrata 1), odmah upravlja
ventilatorom i razglasom bez ikakvog drugog odobrenja — pa je Share listu
vrijedno povremeno pregledati (`login.tailscale.com` → Machines →
`spremiste` → **Unshare** oduzima pristup odmah, bez čekanja).

Tailscale **auth key** (`Settings → Keys`) iz vlastite konzole nije mehanizam
za dodavanje ljudi naknadno — koristi se jednom, ugrađen u sliku diska pri
prvom podizanju uređaja (DIO 2, korak 2.3 ga odmah revocira jer više ne
treba). Za ljude koji dolaze poslije koristi se Share (gore), ne authkey.

## Daljinski pristup preko WordPressa (bridge)

Treći put pristupa, uz SSH (tailnet-only) i izravno web sučelje (tailnet
preko Share-a) iznad — namijenjen ljudima kojima ne treba Tailscale uopće,
samo prijava na postojeću WordPress stranicu. Potpuno odvojen, dodatan put —
ništa od gore navedenog se ne mijenja ni gasi.

Kratko: WordPress plugin (`wordpress-plugin/rpictl-bridge/`) provjerava
WordPress prijavu i ulogu, pa server-to-server (PHP → Pi, nikad izravno iz
browsera) prosljeđuje naredbe Pi-ju preko **Tailscale Funnela** (javni HTTPS
URL koji Tailscale daje jednom uređaju, bez port-forwardinga na routeru) i
tokena postavljenog u `server.api_token`. Pi mora imati taj token postavljen
— inače je Funnel otvorena rupa bez ikakve zaštite.

Postavljanje na Pi-ju (preko SSH-a, ručno u `config.local.yaml` — ta linija se ne commita):
```bash
# u config.local.yaml:
# server:
#   api_token: "<openssl rand -hex 32>"
sudo systemctl restart rpictl
sudo tailscale funnel 8000
```

Puni koraci (WordPress strana, FTP upload, dodjela pristupa ljudima) su u
`wordpress-plugin/rpictl-bridge/README.md`.
