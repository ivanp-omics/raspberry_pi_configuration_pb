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
pip install -r requirements.txt
```

## Pokretanje

```bash
python -m rpictl
```

Otvori <http://127.0.0.1:8000>. `sim_speed: 60` znači da jedna simulirana
minuta traje jednu stvarnu sekundu — cijeli dan vidiš u 24 minute, pa
ventilator kroz nekoliko minuta prijeđe puni ciklus paljenja i gašenja.

```bash
pytest          # 24 testa, sve u milisekundama
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
POST /api/sim/fault  {"freeze": true}     samo u simulaciji
WS   /ws                          događaji uživo
```

## Prelazak na Raspberry Pi

1. `simulate: false` i `sim_speed: 1.0` u `config.yaml`
2. `pip install gpiozero RPi.GPIO smbus2 bme680`
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
je u **`tailscale_Readme.md`** (uloge ADMIN / INSTALATER / KORISNIK) — ovo je
samo dio koji se nadovezuje na to, specifično za **web sučelje rpictl-a** na
portu 8000 (za razliku od SSH pristupa uređaju, koji je posve odvojena stvar).

`server.host` u `config.yaml` mora biti `0.0.0.0` (ne `127.0.0.1`) da bi server
uopće slušao na mreži. Uređaj je spojen i na obični Ethernet (ne samo
Tailscale) — ako ne želiš da razglas/ventilacija budu dohvatljivi i s te LAN
mreže (npr. cijeli ured/skladište), veži server konkretno na tailscale
sučelje (`100.x.y.z`) umjesto na `0.0.0.0`.

**Kako netko dobije pristup:** to je `tailscale_Readme.md` DIO 3, "Vrata 1 —
mreža" — ADMIN na `login.tailscale.com` → Machines → `spremiste` → **Share**,
i pošalje link KORISNIKU. Čim KORISNIK prihvati link svojim Tailscale
računom, u browseru otvara `http://spremiste:8000` (Tailscale MagicDNS
razrješava ime, isto kao `ssh ivan@spremiste`; `100.x.y.z` iz `tailscale
status` radi kao rezerva ako ime ne prođe) i ima **odmah** puni pristup
razglasu, glazbi i ventilaciji.

Bitna razlika od SSH-a: SSH traži i "Vrata 2" (KORISNIKOV javni ključ ručno
dodan u `~/.ssh/authorized_keys` na uređaju, DIO 3 koraci 3.6–3.7) prije nego
itko uđe u shell. Web sučelje rpictl-a tu drugu prepreku **nema** — nema
prijave, tokena ni računa u samoj aplikaciji (namjerna odluka, vidi
`services/announcer.py`/`app.py` — nula auth koda). Znači: čim je netko
Share-an na `spremiste` (Vrata 1), odmah upravlja ventilatorom i razglasom
bez ikakvog drugog odobrenja — to je jedina stvarna "brava" ovdje, pa je Share
listu vrijedno povremeno pregledati (`login.tailscale.com` → Machines →
`spremiste` → **Unshare** oduzima pristup odmah, bez čekanja).

Tailscale **auth key** (`Settings → Keys`) iz vlastite konzole nije mehanizam
za dodavanje ljudi naknadno — koristi se jednom, ugrađen u sliku diska pri
prvom podizanju uređaja (DIO 2, korak 2.3 ga odmah revocira jer više ne
treba). Za ljude koji dolaze poslije koristi se Share (gore), ne authkey.
