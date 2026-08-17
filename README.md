<div align="center">

# 🌬️ WinExhale

**The Ultimate Open-Source Windows Debloater, Privacy Engine & Performance Suite**

[![GitHub Release](https://img.shields.io/github/v/release/Th3Gold3nRainbow/WinExhale?style=for-the-badge&logo=github&color=06B6D4)](https://github.com/Th3Gold3nRainbow/WinExhale/releases/latest)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/Th3Gold3nRainbow/WinExhale)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-emerald.svg?style=for-the-badge)](LICENSE)
[![Downloads](https://img.shields.io/github/downloads/Th3Gold3nRainbow/WinExhale/total?style=for-the-badge&color=8B5CF6&logo=github)](https://github.com/Th3Gold3nRainbow/WinExhale/releases)

<p align="center">
  <a href="#-key-features">Features</a> •
  <a href="#-download--installation">Download</a> •
  <a href="#-preview--interface">Preview</a> •
  <a href="#-building-from-source">Build from Source</a> •
  <a href="#-safety--disclaimer">Safety</a> •
  <a href="#-contributing">Contributing</a>
</p>

</div>

---

## 💡 What is WinExhale?

**WinExhale** is a lightweight, modern, and transparent Windows utility designed to strip away bloatware, disable telemetry & tracking, supercharge gaming latency, safely manage startup processes, and reclaim gigabytes of disk space.

Built with Python and a sleek dark CustomTkinter interface, WinExhale gives power users, gamers, and privacy advocates full control over their Windows 10 & 11 environments without confusing scripts or opaque registry cleaners.

> 🛡️ **Safety-First Philosophy**: WinExhale features built-in **System Restore Point** integration and non-destructive backups for all startup items and settings before any modification is made.

---

## ✨ Key Features

### 🚀 1. Windows Debloater
- 🧹 **One-Click UWP App Stripper**: Remove pre-installed OEM apps, Cortana, Bing News/Weather, Feedback Hub, Xbox overlays, and promotional software (Candy Crush, Spotify, etc.).
- 📦 **Safe Batch Removal**: Uses official PowerShell `Remove-AppxPackage` APIs for clean uninstalls without corrupting system dependencies.

### 🔒 2. Privacy & Telemetry Hardening
- 🛑 **Telemetry Neutralizer**: Disable `DiagTrack` (Connected User Experiences and Telemetry) and `dmwappushservice`.
- 🛡️ **Diagnostic & Ad Tracking Blocking**: Disable Advertising ID, Windows Error Reporting (WER), diagnostics data collection, and customer telemetry.
- 🔍 **Cloud Search & Cortana Lockdown**: Stop Windows Search from sending local keystrokes and queries to Bing servers.

### ⚡ 3. Performance & Game Mode
- 🎮 **High-Performance Power Optimization**: Automatically enable ultra-low latency power plans tuned for gaming and heavy workloads.
- 🏎️ **Service Streamlining**: Toggle SysMain (Superfetch) and indexing services for responsiveness on SSDs/NVMe drives.
- 🔄 **One-Click Restore**: Easily revert to Windows default performance profiles at any time.

### 🛡️ 4. Windows Annoyances (QoL Tweaks)
- 🚫 **Disable Sticky Keys Prompt**: Permanently disables the intrusive Shift 5x popup in games (`Flags = 506`).
- 🔎 **Start Menu Web Search Stripper**: Stops Windows Search from querying Bing servers.
- 🔕 **Lock Screen Ads & Tips**: Cleans up lock screen sponsored banners and notifications.
- 📰 **Taskbar Widgets & News Ticker**: Disables intrusive Windows 11/10 news widgets.
- 📁 **Show File Extensions & Hidden Files**: Automatically enables full file extensions and hidden items in File Explorer.

### 🌐 5. DNS Optimizer & Live Latency Benchmark
- ⏱️ **Live Resolver Benchmarking**: Pings top DNS providers (Cloudflare, Google, Quad9, AdGuard) with real-time color badges (Green < 20ms, Yellow < 50ms, Red > 50ms).
- 🔄 **Dynamic Adapter Switching**: Identifies active network interfaces and applies optimal DNS settings via PowerShell.
- 🔁 **DHCP One-Click Reset**: Instant rollback to automatic DNS with automatic resolver cache flush (`ipconfig /flushdns`).

### 📦 6. App Installer (Winget Integration)
- 🚀 **One-Click Multi-App Deployment**: Install essential software seamlessly across 5 categories (Browsers, Utilities, Media, Gaming, Dev Tools).
- 📜 **Live Terminal Output**: Streams real-time download and installation progress directly into the in-app console.

### 📋 7. Safe Startup Manager
- 🔍 **Unified Registry & Folder Scanner**: Inspects `HKCU`/`HKLM` run keys and user startup directories.
- 🛡️ **Non-Destructive Toggle**: Disabling an item preserves the full path in registry backups (`Run\WinExhale_Disabled`) and file backups in `%APPDATA%\WinExhale\StartupBackup`. Toggling back immediately restores the exact original entry.

### 🧹 8. Deep Junk & Cache Cleaner
- 💾 **System Temp Cleanup**: Purges locked and stale `%TEMP%`, `C:\Windows\Temp`, and log dumps.
- 🌐 **DNS & Network Flush**: Clears local resolver caches to resolve connectivity hiccups.
- 🎮 **Shader & GPU Cache Refresh**: Flushes obsolete DirectX/GPU shader caches for stutter-free gaming.
- 📊 **Real-Time Savings Counter**: Displays exact freed disk space live.

### 🌐 9. Bilingual & Modern UI
- 🎨 **Sleek Cyber-Dark Theme**: Native dark theme with vibrant cyan accents.
- 🌍 **Full Localization**: Seamless toggle between **English** and **Français** with instant UI refresh.
- 📜 **Live Threaded Console**: Timestamped, color-coded execution output that never freezes the main interface.

---

## 📸 Preview / Interface

<div align="center">
  <img src="app_logo.png" alt="WinExhale UI Preview" width="700" style="border-radius: 10px; box-shadow: 0 8px 30px rgba(0,0,0,0.5);">
  <p><em>Modern, responsive CustomTkinter UI with real-time logging and instant actions.</em></p>
</div>

---

## 📥 Download & Installation

### Option A: Setup Installer (Recommended)
Download the latest multi-language installer wizard with desktop shortcuts and automatic uninstaller:
1. Go to the [**Latest GitHub Release**](https://github.com/Th3Gold3nRainbow/WinExhale/releases/latest).
2. Download `WinExhale_Setup.exe`.
3. Run the installer and follow the setup wizard.

### Option B: Standalone Portable EXE
1. Download `WinExhale.exe` directly from the [**Releases Page**](https://github.com/Th3Gold3nRainbow/WinExhale/releases/latest).
2. Run `WinExhale.exe` anywhere (USB drive, Desktop). Requires Administrator elevation (UAC prompt).

---

## 🛠️ Building from Source

### Prerequisites
- **Windows 10 / 11**
- **Python 3.10+** ([python.org](https://www.python.org/))
- **Git**

### 1. Clone the Repository
```powershell
git clone https://github.com/Th3Gold3nRainbow/WinExhale.git
cd WinExhale
```

### 2. Install Dependencies
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Generate Assets (Icons & Logo)
```powershell
python generate_assets.py
```

### 4. Run Locally
```powershell
python main.py
```

### 5. Compile Standalone `.exe` (PyInstaller)
```powershell
pyinstaller WinExhale.spec --noconfirm --clean
```
The executable will be located in `dist\WinExhale.exe`.

### 6. (Optional) Build Inno Setup Installer
Download and install [Inno Setup 6](https://jrsoftware.org/isinfo.php), then run:
```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```
Output: `installer_output\WinExhale_Setup.exe`.

---

## 🛡️ Safety, Security & Disclaimer

- **Administrator Privileges**: WinExhale manages system services, AppX packages, and registry keys. An elevated UAC prompt is requested on launch.
- **System Restore Point**: We strongly advise creating a System Restore point before running batch operations. A dedicated **"Create Restore Point"** button is built into the application header.
- **Disclaimer**: WinExhale is open-source software provided under the MIT License. Use responsibly. Always review tweaks before applying them to mission-critical systems.

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!
1. Fork the Project.
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`).
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the Branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

Please check our [Issue Tracker](https://github.com/Th3Gold3nRainbow/WinExhale/issues) to report bugs or request new features.

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more information.

<div align="center">
  <sub>Made with ❤️ for the Windows open-source community.</sub>
</div>
