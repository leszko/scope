#!/bin/bash
# Post-installation script for Linux

# Fix chrome-sandbox permissions (required for Electron sandbox)
INSTALL_DIR="/opt/DaydreamScope"
if [ -f "$INSTALL_DIR/chrome-sandbox" ]; then
    chmod 4755 "$INSTALL_DIR/chrome-sandbox"
    echo "Set chrome-sandbox permissions to 4755"
fi

# Update desktop database
if command -v update-desktop-database > /dev/null 2>&1; then
    update-desktop-database -q
fi

# Update icon cache
if command -v gtk-update-icon-cache > /dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi

# Update MIME database
if command -v update-mime-database > /dev/null 2>&1; then
    update-mime-database /usr/share/mime || true
fi

exit 0
