#!/bin/bash
# provision-rpictl.sh - run ON THE PI as the login user (needs sudo):
#     bash provision-rpictl.sh
# Installs rpictl into /opt/rpictl in SIMULATION mode as a systemd service.
# Idempotent: re-running updates the code and restarts the service.
set -euo pipefail

REPO="https://github.com/ivanp-omics/raspberry_pi_configuration_pb.git"
APP_DIR="/opt/rpictl"
RUN_USER="$(id -un)"

echo "== [1/9] apt packages =="
sudo apt-get update -q
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q \
  git curl python3 python3-venv python3-pip \
  alsa-utils espeak-ng mpv i2c-tools \
  python3-gpiozero python3-lgpio python3-smbus2

echo "== [2/9] tailscale check =="
if command -v tailscale >/dev/null 2>&1; then
  echo "  tailscale je instaliran: $(tailscale version | head -n1)"
else
  echo "  UPOZORENJE: tailscale nije pronaden na ovom sustavu."
  echo "  Ovaj uredjaj nece biti dostupan preko tailneta dok se rucno ne instalira i pokrene:"
  echo "    curl -fsSL https://tailscale.com/install.sh | sh"
  echo "    sudo tailscale up"
fi

echo "== [3/9] code -> $APP_DIR =="
if [ -d "$APP_DIR/.git" ]; then
  sudo -u "$RUN_USER" git -C "$APP_DIR" pull --ff-only
else
  sudo mkdir -p "$APP_DIR"
  sudo chown "$RUN_USER:$RUN_USER" "$APP_DIR"
  git clone "$REPO" "$APP_DIR"
fi

echo "== [4/9] I2C interface =="
CONFIG_TXT=""
for candidate in /boot/firmware/config.txt /boot/config.txt; do
  [ -f "$candidate" ] && CONFIG_TXT="$candidate" && break
done
if [ -n "$CONFIG_TXT" ] && ! grep -qE "^dtparam=i2c_arm=on" "$CONFIG_TXT"; then
  echo "  dodajem dtparam=i2c_arm=on u $CONFIG_TXT (potreban restart da se primijeni)"
  echo "dtparam=i2c_arm=on" | sudo tee -a "$CONFIG_TXT" >/dev/null
fi
if [ ! -e /dev/i2c-1 ]; then
  echo "  /dev/i2c-1 ne postoji - primjenjujem poznati zaobilazak cloud-init buga"
  echo "i2c-dev" | sudo tee /etc/modules-load.d/i2c-dev.conf >/dev/null
  sudo modprobe i2c-dev || true
fi
if [ ! -e /dev/i2c-1 ]; then
  echo "  NAPOMENA: /dev/i2c-1 i dalje ne postoji - vjerojatno treba restart Pija da se primijeni dtparam iz $CONFIG_TXT"
fi

echo "== [5/9] korisnicke grupe (gpio/i2c/audio) =="
sudo usermod -aG gpio,i2c,audio "$RUN_USER"

echo "== [6/9] python venv (sees apt-installed gpiozero/lgpio/smbus2) =="
cd "$APP_DIR"
[ -x .venv/bin/python ] || python3 -m venv --system-site-packages .venv
.venv/bin/pip install -q --upgrade pip
# requirements.txt is runtime-only by design (dev tools live in
# requirements-dev.txt). Installing the file instead of a hand-kept list is
# deliberate: a dependency added to the code but not here means the service
# does not start at all - FastAPI raises while building the routes, systemd
# retries forever, and the reason is buried in journalctl.
.venv/bin/pip install -q -r requirements.txt
# BME680 driver - only used when simulate: false, harmless to have ready
.venv/bin/pip install -q bme680

echo "== [7/9] config.local.yaml (tracked in git - real hardware settings) =="
# config.local.yaml is now committed to the repo (real hardware settings tracked
# in git history), so it should already be here after step [3/9]'s git pull/clone.
# The one field that is NEVER committed with a real value is api_token - fill it
# in by hand over SSH on the device itself, then leave that one line uncommitted.
if [ ! -f config.local.yaml ]; then
  echo "  GRESKA: config.local.yaml ne postoji u $APP_DIR." >&2
  echo "  Ocekivano je da dodje iz gita (config.local.yaml je trackan). Provjeri checkout." >&2
  exit 1
fi
if ! grep -qE '^\s*api_token:\s*"[^"]+"' config.local.yaml; then
  echo "  UPOZORENJE: server.api_token je prazan u config.local.yaml."
  echo "  Bez njega, svatko na istoj mrezi/tailnetu moze upravljati ventilacijom i razglasom."
  echo "  Postavi ga rucno preko SSH-a: openssl rand -hex 32   (pa nano config.local.yaml, ne commitaj tu liniju)"
fi
grep -nE "^simulate:|relay_active_high|i2c_address|volume=|temp_on_c|temp_off_c" config.local.yaml \
  || echo "  (nijedan ocekivani kljuc nije pronaden - config.local.yaml je vjerojatno rucno izmijenjen, provjeri ga rucno)"
mkdir -p data media/music

echo "== [8/9] systemd service (user=$RUN_USER, dir=$APP_DIR) =="
sudo tee /etc/systemd/system/rpictl.service >/dev/null <<UNIT
[Unit]
Description=rpictl - upravljanje spremistem
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python -m rpictl --config $APP_DIR/config.local.yaml
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable rpictl >/dev/null
sudo systemctl restart rpictl

echo "== [9/9] health check =="
for i in $(seq 1 20); do
  if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -s http://127.0.0.1:8000/api/health || echo "  (health endpoint nije odgovorio - vidi status/logove ispod)"
echo
systemctl --no-pager --lines=5 status rpictl | head -12 || true
IP=$(hostname -I | awk '{print $1}')
echo
echo "Done. Web UI:  http://$IP:8000   (or http://$(hostname).local:8000)"
echo "Logs:          journalctl -u rpictl -f"
echo "Config edits:  nano $APP_DIR/config.local.yaml && sudo systemctl restart rpictl"
