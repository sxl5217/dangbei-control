# Dangbei Remote Control

English Version | [中文版本](README-zh.md)

A LAN-only remote control for Dangbei devices, controlled via a mobile browser.

**Current Version: v1.0.0**

## Features

- Mobile-optimized UI with circular D-pad design
- Auto-connect to known device on startup
- Scan prioritizes known device first, then full network scan
- Mobile browser access, no app installation required
- Supports all common remote keys (including quick shutdown and reboot)
- Long press for repeated commands (D-pad, volume keys)
- Anti-mistouch design (slide out of button area to cancel)
- Auto-save configuration, persists after restart
- Volume adjustment from 0-15 levels
- Persistent WebSocket connection to reduce handshake overhead
- State caching for fast status queries
- Volume slider drag state control to prevent operation conflicts
- Network scanning using ipaddress module, supports custom network segments
- Semaphore concurrency control
- Device status monitoring: 3-second check when online, 10-second check when offline
- Auto-reboot on first daily device startup (5-second delay to ensure initialization)

## Quick Start

### Method 1: Using uv (Recommended)

1. Install uv (if not installed):

**Windows:**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Linux/Mac:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Run the project:
```bash
uv run python server.py
```

### Method 2: Using Startup Scripts

**Windows:** Double-click `start.bat`

**Linux/Mac:**
```bash
chmod +x start.sh
./start.sh
```

### Method 3: Manual Startup

1. Install dependencies:
```bash
pip install aiohttp websockets
```

2. Run the service:
```bash
python server.py
```

## Usage

1. Ensure the computer running this program and the Dangbei projector are on the same LAN
2. After starting the service, access the displayed address in your mobile browser (e.g., `http://192.168.1.100:8080`)
3. Click the top status bar when disconnected to start scanning
4. Click the top status bar when connected to view device information
5. Start using the remote control

## Project Structure

```
dangbei-control/
├── server.py          # Python backend service
├── index.html         # Frontend page
├── favicon.svg        # Website icon
├── css/
│   └── style.css      # Style file
├── js/
│   └── main-simple.js # Frontend logic
├── .data/
│   └── config.json    # Configuration file
├── start.bat          # Windows startup script
├── start.sh           # Linux/Mac startup script
├── pyproject.toml     # uv project configuration
└── README.md          # Documentation
```

## Configuration

- Default port: 8080
- Configuration file: `.data/config.json` (saves known device, volume, last reboot date)
- Port can be modified via `--port` parameter: `uv run python server.py --port 9090`
- Custom scan network: Add `"scan_network": "192.168.1.0/24"` field in config file (optional)

## Execution Flow

1. **On startup**: Try to connect to known device from config file
2. **If fails**: Set state to offline, wait for user to trigger scan
3. **User clicks top bar (disconnected)**: Try known device first, then full network scan if fails
4. **User clicks top bar (connected)**: Open bottom device list
5. **Command received**: Send directly to device
6. **Send fails**: Mark device as offline, show offline confirmation dialog
7. **First daily online**: After detecting device changes from offline to online, wait 5 seconds and auto-reboot once

## Key Description

| Key | Function |
|-----|----------|
| Power | Toggle power |
| Quick Shutdown | Send shutdown sequence |
| Reboot | Send reboot sequence |
| Sidebar | Side menu |
| Volume +/- | Volume adjustment (supports long press) |
| D-pad | Up/Down/Left/Right (supports long press) |
| OK | Confirm |
| Home | Return to home |
| Menu | Open menu |
| Back | Go back |
| Find Remote | Make device play a sound |

## Known Limitations

Due to Dangbei device protocol limitations, the current absolute physical volume cannot be read directly, only relative increase/decrease commands can be sent. If the physical remote is used to adjust volume, the volume display on the webpage will be out of sync with the device's physical volume. It's recommended to consistently use the webpage for volume control.

## License

[MIT License](LICENSE)
