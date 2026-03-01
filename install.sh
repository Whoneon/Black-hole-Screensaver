#!/usr/bin/env bash
# =============================================================================
#  install.sh — Installa il Black Hole Screensaver su Ubuntu
# =============================================================================
set -e
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; NC="\033[0m"
info() { echo -e "${GREEN}[✓]${NC} $*"; }

echo ""
echo "════════════════════════════════════════════"
echo "   Black Hole Screensaver — Installer"
echo "════════════════════════════════════════════"
echo ""

command -v python3 &>/dev/null || { echo "Python 3 richiesto."; exit 1; }

info "Installazione dipendenze di sistema..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pip python3-venv \
    libgl1-mesa-dev libgles2-mesa-dev libsdl2-dev \
    xscreensaver xscreensaver-gl

INSTALL_DIR="$HOME/.local/share/blackhole-screensaver"
mkdir -p "$INSTALL_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SCRIPT_DIR/blackhole_screensaver.py" "$INSTALL_DIR/"

info "Creazione ambiente virtuale Python..."
python3 -m venv "$INSTALL_DIR/venv"
source "$INSTALL_DIR/venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet moderngl pygame numpy
deactivate

WRAPPER="$INSTALL_DIR/blackhole-screensaver"
cat > "$WRAPPER" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/venv/bin/activate"
exec python3 "$DIR/blackhole_screensaver.py" "$@"
EOF
chmod +x "$WRAPPER"

# Registra con xscreensaver
XSCREENSAVER_RC="$HOME/.xscreensaver"
if [ -f "$XSCREENSAVER_RC" ] && ! grep -q "blackhole-screensaver" "$XSCREENSAVER_RC"; then
    sed -i '/^programs:/a\\  GL:                   blackhole-screensaver -root   \\n\' "$XSCREENSAVER_RC"
fi

# Menu applicazioni
cat > "$HOME/.local/share/applications/blackhole-screensaver.desktop" <<DESK
[Desktop Entry]
Version=1.0
Name=Black Hole Screensaver
Comment=Simulazione fisica di un buco nero di Schwarzschild
Exec=$WRAPPER
Icon=video-display
Terminal=false
Type=Application
Categories=Utility;Screensaver;
DESK

# Disinstallatore
cat > "$INSTALL_DIR/uninstall.sh" <<UNINST
#!/usr/bin/env bash
rm -rf "$INSTALL_DIR"
rm -f "$HOME/.local/share/applications/blackhole-screensaver.desktop"
sed -i '/blackhole-screensaver/d' "$HOME/.xscreensaver" 2>/dev/null || true
echo "Rimosso."
UNINST
chmod +x "$INSTALL_DIR/uninstall.sh"

echo ""
echo "════════════════════════════════════════════"
info "Installazione completata!"
echo ""
echo "  Test:             $WRAPPER"
echo "  Configurazione:   xscreensaver-settings"
echo "  Avvio demone:     xscreensaver &"
echo "  Timeout:          ./set_timeout.sh 5"
echo "  Disinstalla:      $INSTALL_DIR/uninstall.sh"
echo ""
echo "  Parametri avanzati:"
echo "    --spin 0.9          (buco nero in rapida rotazione)"
echo "    --inclination 0.1   (vista quasi di profilo)"
echo "    --inclination 1.2   (vista quasi dall'alto)"
echo "════════════════════════════════════════════"
