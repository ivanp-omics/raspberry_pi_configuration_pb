# README — Raspberry Pi spremište

## Uloge

| Uloga | Tko je | Što radi |
|---|---|---|
| **ADMIN** | vlasnik uređaja | priprema sliku, upravlja pristupom, administrira sustav |
| **INSTALATER** | osoba na lokaciji | zapisuje karticu, spaja i uključuje uređaj |
| **KORISNIK** | dodatna osoba | dobiva pristup naknadno |

## Isporučene datoteke

| Datoteka | Sadržaj |
|---|---|
| `raspios-trixie-arm64-lite.7z` | Slika operativnog sustava (~1 GB) |
| `raspios-trixie-arm64-lite.txt` | Kontrolni broj (SHA256) za provjeru |

## Pregled postupka

```
ADMIN                INSTALATER              ADMIN
priprema slike   →   zapisuje karticu   →   spaja se preko SSH-a
                     spaja uređaj
                     uključuje
```

---

# DIO 1 — Postavljanje uređaja

**Izvodi:** INSTALATER · **Trajanje:** oko 40 minuta

**Potrebno:** računalo, microSD kartica 64 GB, čitač kartica, Raspberry Pi,
mrežni kabel, napajanje.

## Korak 1.1 — Provjera datoteke

Otvori `raspios-trixie-arm64-lite.txt`. Unutra je niz od 64 znaka.

**Windows** — otvori PowerShell (Start → upiši `powershell`), pa u mapi gdje je
datoteka:

    Get-FileHash raspios-trixie-arm64-lite.7z -Algorithm SHA256

**macOS** — otvori Terminal (Cmd + razmak → `terminal`):

    shasum -a 256 raspios-trixie-arm64-lite.7z

**Linux:**

    sha256sum raspios-trixie-arm64-lite.7z

Usporedi ispisani niz s onim iz `.txt` datoteke. Moraju biti **identični**.

Ako nisu, datoteka se oštetila pri prijenosu. Javi ADMINU da je pošalje
ponovno. **Ne nastavljaj s neispravnom datotekom** — kartica će se zapisati bez
greške, a uređaj se neće dignuti.

## Korak 1.2 — Raspakiravanje

Instaliraj alat za `.7z` arhive:

- **Windows** — 7-Zip s `7-zip.org`
- **macOS** — Keka s `keka.io`
- **Linux** — `sudo apt install p7zip-full`

Raspakiraj arhivu. Dobiješ datoteku s nastavkom **`.img`**, oko 2.8 GB.

> Obavezan korak. Raspberry Pi Imager ne otvara `.7z` arhive.

## Korak 1.3 — Raspberry Pi Imager

Skini s `raspberrypi.com/software` i instaliraj. Službeni je i besplatan.

## Korak 1.4 — Zapisivanje na karticu

> **UPOZORENJE:** sve na kartici bit će nepovratno obrisano. Provjeri dvaput da
> si odabrao karticu, a ne vanjski disk ili USB stick.

1. Ubaci karticu u čitač
2. Pokreni Raspberry Pi Imager
3. **Choose device** → Raspberry Pi 3
4. **Choose OS** → skrolaj skroz dolje → **Use custom** → odaberi raspakiranu
   **`.img`** datoteku
5. **Choose storage** → microSD kartica
6. **Next**

### Točka 7 je kritična

Pojavi se pitanje **"Would you like to apply OS customisation settings?"**

Odaberi **NO** (ili "No, clear settings").

Slika već sadrži sve postavke. Ako odabereš da, Imager ih pregazi i uređaj se
neće moći spojiti — postupak ide ispočetka.

8. Potvrdi upozorenje o brisanju
9. Zapisivanje traje 10–15 minuta
10. Pusti da Imager odradi i provjeru (**Verifying**) do kraja

## Korak 1.5 — Spajanje

**Redoslijed je bitan:**

1. Izvadi karticu iz čitača i **ubaci je u Raspberry Pi**
   (utor s donje strane pločice)
2. **Spoji mrežni kabel** — jedan kraj u Pi, drugi u ruter
3. **Tek sada spoji napajanje**

## Korak 1.6 — Provjera

| Lampica | Značenje |
|---|---|
| Crvena, stalno svijetli | Ima struje — dobro |
| Zelena, treperi nepravilno | Čita s kartice — dobro |
| Zelena uopće ne treperi | Problem s karticom |
| Crvena treperi ili se gasi | Slabo napajanje |

Zelene lampice kraj mrežne utičnice moraju se upaliti čim spojiš kabel.

**Prvo pokretanje traje 15–20 minuta.** Uređaj se pritom **jednom sam
restarta** — to je normalno. Skida i instalira softver preko interneta, pa
trajanje ovisi o brzini veze.

**Ne gasi ga i ne vadi struju.** Kad prođe 20 minuta, javi ADMINU da je
uključeno.

## Rješavanje problema

| Simptom | Uzrok i rješenje |
|---|---|
| Nijedna lampica | Napajanje ili kabel |
| Crvena svijetli, zelena ne trepće | Kartica loše zapisana ili nije dogurana. Izvadi je i vrati. Ako ne pomogne, ponovi korak 1.4 |
| Sve izgleda dobro, ne javlja se | Provjeri da kabel ide u ruter i da se zelene lampice kraj mrežnog priključka pale |

**Ne mijenjaj ništa drugo na uređaju.** Ako nešto ne ide, javi što vidiš.

---

# DIO 2 — Prvo spajanje

**Izvodi:** ADMIN

## Korak 2.1 — Tailscale na vlastitom računalu

Instaliraj s `tailscale.com/download`.

Instalacija i prijava su dva odvojena koraka. Nakon instalacije klikni ikonu u
traci zadataka (može biti skrivena pod strelicom) → **Log in** → prijavi se u
browseru.

Provjera:

    tailscale status

Moraš vidjeti barem vlastito računalo, s adresom koja počinje sa `100.`. Ako
piše `Logged out`, prijava nije dovršena.

`spremiste` se neće pojaviti dok uređaj stvarno ne proradi.

## Korak 2.2 — Spajanje

Nakon što INSTALATER javi da je uključeno:

    tailscale status
    ssh ivan@spremiste

Prvi put pita o "authenticity of host" — upiši `yes`.

Ako naziv ne radi, uzmi `100.x.y.z` adresu iz `tailscale status`:

    ssh ivan@100.x.y.z

Ako se `spremiste` uopće ne pojavi ni nakon 20 minuta, uređaj vjerojatno nije
dobio internet. Provjeri s INSTALATEROM da kabel ide u ruter.

## Korak 2.3 — Obavezne radnje odmah

**1. Promijeni privremenu lozinku**

    passwd

**2. Isključi istek ključa uređaja**

`login.tailscale.com` → **Machines** → `spremiste` → tri točkice →
**Disable key expiry**

Bez ovoga uređaj za oko 180 dana tiho ispadne iz mreže i pristup je izgubljen.
Ovo je jedina stvar koja može oduzeti pristup a da ništa nije pogrešno
napravljeno.

**3. Revokiraj auth ključ**

`login.tailscale.com` → **Settings** → **Keys** → revoke.

Uređaj je već u mreži, ključ više ne treba, a putovao je internetom.

**4. Provjeri da je instalacija prošla**

    ls /var/log/storage-room-provisioned

Ako datoteka postoji, sve je odrađeno. Ako ne:

    sudo cat /var/log/cloud-init-output.log

## Korak 2.4 — Provjera hardvera

    i2cdetect -y 1              # senzor na 0x76 ili 0x77
    vcgencmd get_throttled      # mora biti throttled=0x0
    vcgencmd measure_temp       # temperatura procesora
    ip a                        # mrežne adrese
    timedatectl                 # sat sinkroniziran (nema RTC baterije)

Ako `get_throttled` javi nešto različito od `0x0`, napajanje je preslabo.
To daje nasumične reboote i čudno ponašanje koje se lako pripiše softveru.

---

# DIO 3 — Dodavanje korisnika

**Izvodi:** ADMIN i KORISNIK zajedno · **8 koraka**

KORISNIK radi korake 3.1–3.3 i 3.8. ADMIN radi 3.4–3.7.

## Kako pristup funkcionira

Da bi KORISNIK došao do uređaja, mora proći dvoje vrata. **Oboje otvara
ADMIN.**

| | Što otvara | Gdje se otvara |
|---|---|---|
| **Vrata 1 — mreža** | vidljivost uređaja | Tailscale konzola |
| **Vrata 2 — pristup** | ulazak u sustav | na samom uređaju |

Otvaranje samo prvih vrata nije dovoljno — KORISNIK će vidjeti uređaj, ali
`ssh` će ga odbiti.

## Kako ključevi rade

Kad KORISNIK pokrene `ssh-keygen`, nastanu dvije datoteke:

| Datoteka | Vrsta | Gdje ide |
|---|---|---|
| `id_ed25519` | **privatni** | ostaje na njegovom računalu, zauvijek |
| `id_ed25519.pub` | **javni** | šalje se ADMINU |

Javni ključ smije se slobodno slati mailom ili chatom. Sam po sebi ne otvara
ništa — koristan je samo onome tko ima odgovarajući privatni.

**Privatni ključ nikad ne napušta računalo KORISNIKA.**

## Korak 3.1 — KORISNIK otvara terminal

*Tekst za slanje KORISNIKU:*

> **Windows:** pritisni tipku Windows, upiši `powershell`, Enter.
>
> **macOS:** pritisni Cmd + razmak, upiši `terminal`, Enter.
>
> **Linux:** pritisni Ctrl + Alt + T.

## Korak 3.2 — KORISNIK generira ključ

*Tekst za slanje KORISNIKU:*

> Zalijepi ovo i pritisni Enter:
>
>     ssh-keygen -t ed25519
>
> Postavit će tri pitanja. **Na svako samo pritisni Enter**, ništa ne upisuj.
>
> Na kraju ispiše "Your identification has been saved" i nacrta sličicu od
> znakova. To znači da je uspjelo.
>
> Ako pita `Overwrite (y/n)?`, već imaš ključ — upiši `n` i prijeđi dalje.

## Korak 3.3 — KORISNIK šalje javni ključ

*Tekst za slanje KORISNIKU:*

> **Windows:**
>
>     type $env:USERPROFILE\.ssh\id_ed25519.pub
>
> **macOS / Linux:**
>
>     cat ~/.ssh/id_ed25519.pub
>
> Ispisat će se **jedan red** koji počinje sa `ssh-ed25519 AAAAC3...` i
> završava tvojim imenom. Kopiraj taj cijeli red i pošalji ga.
>
> Usput instaliraj **Tailscale** s `tailscale.com/download` i napravi
> besplatan račun.

## Korak 3.4 — ADMIN provjerava ključ

| Počinje s | Vrsta | Postupak |
|---|---|---|
| `ssh-ed25519 AAAAC3...` | javni — ispravno | nastavi na 3.5 |
| `-----BEGIN OPENSSH PRIVATE KEY-----` | privatni — pogrešno | vidi dolje |

Mora biti **jedan red**. Ako ih je više, poslana je kriva datoteka.

*Ako je poslan privatni ključ, pošalji KORISNIKU:*

> To je privatni ključ i ne smije napustiti tvoje računalo. Trebam datoteku
> koja završava s `.pub`. Pokreni ponovno naredbu iz prošlog koraka i pošalji
> ono što ispiše.

## Korak 3.5 — ADMIN otvara mrežu (Vrata 1)

1. Otvori `login.tailscale.com`
2. **Machines** u lijevom izborniku
3. Nađi `spremiste`
4. Klikni **tri točkice** desno
5. **Share**
6. Kopiraj link i pošalji ga KORISNIKU

## Korak 3.6 — ADMIN se spaja na uređaj

    ssh ivan@spremiste

Prompt se promijeni iz:

    PS C:\Users\ivanp>

u:

    ivan@spremiste:~ $

**Od tog trenutka sve što se tipka izvršava se na uređaju**, ne na lokalnom
računalu. Isti prozor, naredbe idu preko mreže.

Provjera gdje si: upiši `hostname`. Vraća `spremiste` ako si na uređaju.

## Korak 3.7 — ADMIN dodaje ključ (Vrata 2)

Prompt kaže `ivan@spremiste:~ $`. Upiši:

    nano ~/.ssh/authorized_keys

Otvori se editor s postojećim ključem ADMINA.

1. **Strelica dolje** do zadnjeg reda
2. **End**, pa **Enter** — novi prazan red
3. Zalijepi ključ KORISNIKA — **desni klik** (Windows) ili **Cmd+V** (macOS)
4. Provjeri da je ključ **na svom redu**, ne nastavljen na tuđi
5. **Ctrl+O**, pa **Enter** — sprema
6. **Ctrl+X** — izlazi

Provjera:

    cat ~/.ssh/authorized_keys

Moraju se vidjeti **dva odvojena reda**:

    ssh-ed25519 AAAAC3NzaC1... ivanp@Svjetlan
    ssh-ed25519 AAAAC3NzaC1... korisnik@racunalo

Ako je vidljiv samo jedan dugački red, ključevi su spojeni — vrati se u `nano`
i razdvoji ih.

Izlazak s uređaja:

    exit

## Korak 3.8 — KORISNIK se spaja

*Tekst za slanje KORISNIKU:*

> Klikni link koji si dobio i prihvati ga svojim Tailscale računom.
>
> Zatim u terminalu:
>
>     ssh ivan@spremiste
>
> Prvi put pita o "authenticity of host" — upiši `yes` i pritisni Enter.
>
> Ako se prompt promijeni u `ivan@spremiste:~ $`, spojen si.

## Rješavanje problema

| Poruka | Uzrok | Rješenje |
|---|---|---|
| `Could not resolve hostname` | Tailscale nije aktivan ili share nije prihvaćen | Provjeriti da je Tailscale uključen, ponovno kliknuti link |
| `Permission denied (publickey)` | Ključ nije dobro dodan | ADMIN ponavlja 3.7 i provjerava s `cat` |
| `Connection timed out` | Uređaj ugašen ili bez mreže | Provjeriti stanje uređaja |

## Oduzimanje pristupa

ADMIN se spaja na uređaj:

    nano ~/.ssh/authorized_keys

Kursor na red KORISNIKA, držati **Ctrl+K** dok red ne nestane. **Ctrl+O**,
**Enter**, **Ctrl+X**.

Radi odmah, bez restarta.

Za odsijecanje i na razini mreže: `login.tailscale.com` → **Machines** →
`spremiste` → tri točkice → **Unshare**.

## Zaseban korisnički račun

Gornji postupak daje KORISNIKU pristup pod istim računom kao ADMIN. Ako netko
redovito radi na sustavu i treba vlastiti direktorij i povijest naredbi, ADMIN
na uređaju izvodi:

    sudo adduser korisnik
    sudo usermod -aG sudo,gpio,i2c,audio korisnik
    sudo mkdir -p /home/korisnik/.ssh
    echo "ssh-ed25519 AAAA... korisnik@racunalo" | sudo tee /home/korisnik/.ssh/authorized_keys
    sudo chown -R korisnik:korisnik /home/korisnik/.ssh
    sudo chmod 700 /home/korisnik/.ssh
    sudo chmod 600 /home/korisnik/.ssh/authorized_keys

Tada se spaja s `ssh korisnik@spremiste`.

## Vlastiti uređaji ADMINA

Za mobitel ili drugo računalo na koje se ADMIN prijavljuje **svojim** Tailscale
računom — ništa od gornjih koraka.

Instalira se Tailscale, prijavi se, i `ssh ivan@spremiste` odmah radi. Razlog je
opcija `--ssh` u konfiguraciji: Tailscale sam potvrđuje identitet vlasnika
računa.

Postupak s ključevima potreban je samo za **tuđe** račune.

---

# DIO 4 — Rad na sustavu

**Izvodi:** ADMIN

## VS Code Remote-SSH — glavni alat

Instaliraj **VS Code** i ekstenziju **Remote - SSH**.

`F1` → `Remote-SSH: Connect to Host` → `ivan@spremiste`

Otvori se novi prozor u kojem je uređaj radni direktorij. Datoteke se uređuju
direktno na njemu, terminal u VS Codeu je terminal uređaja, debugger radi na
uređaju. Nema kopiranja ni sinkronizacije.

Radi i na Pi 3 — instalira se mali server na uređaj, sučelje ostaje lokalno.

Za ovaj projekt je najbolji izbor jer hardver postoji samo na uređaju. Kod koji
čita senzor nema smisla pokretati lokalno.

## Git

Lokalno:

    git push

Na uređaju:

    cd ~/storage-room && git pull
    sudo systemctl restart storage-room

Daje povijest izmjena i mogućnost povratka unatrag. Na uređaju u drugom gradu
to je bitna sigurnosna mreža.

## Pojedinačne datoteke

    scp skripta.sh ivan@spremiste:~          # prema uređaju
    scp ivan@spremiste:~/logs/app.log .      # s uređaja

Dobro za skripte i logove, neprikladno kao svakodnevni radni tok.

## tmux

    sudo apt install tmux
    tmux new -s rad

Ako veza pukne, sesija ostaje živa. Povratak: `tmux attach -t rad`.

Bez toga prekid veze prekida i naredbu koja se izvršava — usred `apt upgrade`
to je problem.

## Preporuka

VS Code Remote-SSH za svakodnevni rad, Git kad projekt sazrije, `scp` za
sitnice, `tmux` uvijek.

---

# Prilog — što je u slici

Slika je Raspberry Pi OS **Lite** (64-bit, Trixie) — bez desktopa,
administrira se isključivo preko SSH-a.

Konfiguracija je u `user-data` na boot particiji (cloud-init) i u `config.txt`.

## Iz `config.txt`

| Redak | Svrha |
|---|---|
| `dtparam=i2c_arm=on` | I2C sabirnica za senzor |
| `dtparam=audio=on` | 3.5 mm audio izlaz |
| `gpio=17=op,dh` | GPIO17 na visoko **prije nego OS krene** |

Zadnji redak je sigurnosni. Ventilator radi kad relej **nije** pobuđen (spojen
na NC kontakt). Bez ovog retka pin bi tijekom cijelog boota bio neodređen, a
većina opto relejnih modula reagira na nisko — pa bi ventilator stajao pri
svakom pokretanju i restartu.

Ako se ispostavi da je modul obrnute logike, `dh` se mijenja u `dl`. Traži
reboot.

## Iz `user-data`

- korisnik `ivan` sa SSH ključem ADMINA, bez lozinke preko SSH-a
- I2C sučelje preko `rpi:` modula
- osnovni paketi
- ograničenje journald zapisa na 64 MB (čuva SD karticu)
- hardverski watchdog — uređaj se sam resetira ako se objesi
- swap isključen
- Tailscale instaliran i prijavljen

## Poznata ograničenja

**Nema RTC baterije.** Bez interneta uređaj nakon nestanka struje ne zna koliko
je sati. Rješava se NTP-om, što radi čim ima mrežu.

**SD kartica je potrošni dio.** Journald je ograničen i swap isključen upravo
zbog toga, ali kartica ostaje najslabija karika. Backup slike se isplati.

**Nakon svake izmjene u `config.txt` prvo provjeriti da se uređaj vratio**,
prije sljedeće izmjene. Uređaj je u drugom gradu — greška koja spriječi boot
znači da netko mora fizički izvaditi karticu.
