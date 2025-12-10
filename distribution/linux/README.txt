Godoty - AI Assistant for Godot Game Engine
Version: 1.0.0
Platform: Linux (Ubuntu 20.04+, Fedora 35+)

INSTALLATION:
1. Copy Godoty to /usr/local/bin/ or ~/bin/
2. Make executable: chmod +x Godoty
3. Run: ./Godoty or just: Godoty
4. The app will create ~/.godoty/ folder on first run
5. Open the app and configure your OpenRouter API key in the settings panel

REQUIREMENTS:
- GTK 3.0+ with WebKit2GTK
- GObject Introspection
- OpenRouter API key (get from https://openrouter.ai/)

Install dependencies:
# Ubuntu/Debian
sudo apt install libgtk-3-0 libwebkit2gtk-4.0-37 gir1.2-webkit2-4.0

# Fedora
sudo dnf install gtk3 webkit2gtk3

# Arch Linux
sudo pacman -S gtk3 webkit2gtk

TROUBLESHOOTING:
- If the app won't start, run from terminal to see errors

- If you see GTK-related errors:
  Check that all GTK dependencies are installed

- If you see WebKit errors:
  Install webkit2gtk and gir1.2-webkit2-4.0 packages

USAGE:
- Run ./Godoty from the terminal
- The app will open a window with the Godoty interface
- Connect to your Godot project using the Godot plugin
- Use the AI assistant to help with your game development

For more information, visit: https://github.com/your-repo/godoty
