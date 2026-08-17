"""
WinExhale — Windows Debloater, Privacy & Performance Suite (v1.1.0)

Features
  * English / French UI, chosen on first launch, stored in winexhale_config.json
  * Dark theme with cyan accents (customtkinter)
  * Auto elevation to Administrator via ShellExecuteW
  * Tabs: UWP debloat, privacy & telemetry, performance, startup manager,
    junk cleaner
  * Timestamped live console, all system work in background threads

Runtime requirements:  pip install customtkinter pillow
"""

import ctypes
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import winreg
from datetime import datetime

import customtkinter as ctk

try:
    from PIL import Image
except ImportError:          # logo is optional; the app still runs without Pillow
    Image = None

# --windowed PyInstaller builds have no console: stdout/stderr are None and the
# underlying handles are invalid. Anything that prints (e.g. tkinter's callback
# exception reporter) then dies with OSError [WinError 6], so patch them first.
if getattr(sys, "frozen", False):
    for _name in ("stdout", "stderr", "__stdout__", "__stderr__"):
        if getattr(sys, _name, None) is None:
            setattr(sys, _name, open(os.devnull, "w"))

APP_NAME = "WinExhale"
APP_VERSION = "1.1.0"

# ---------------------------------------------------------------- palette ---
COL_BG = "#0B1220"
COL_CARD = "#101B2D"
COL_CARD_2 = "#16233A"
COL_ACCENT = "#06B6D4"
COL_ACCENT_HOVER = "#0891B2"
COL_ACCENT_DARK = "#0E7490"
COL_TEXT = "#E8F0FA"
COL_TEXT_DIM = "#8FA3BF"
COL_SUCCESS = "#34D399"
COL_WARN = "#FBBF24"
COL_ERROR = "#F87171"
COL_CONSOLE_BG = "#0A0F1B"
COL_ON_ACCENT = "#052530"

FONT_FAMILY = "Segoe UI"
FONT_MONO = "Consolas"

HIGH_PERF_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
BALANCED_GUID = "381b4222-f694-41f0-9685-ff5bb260df2"

CREATE_NO_WINDOW = 0x08000000

# ------------------------------------------------------------ paths/config ---

def base_dir():
    """Writable directory for config.json (exe dir when frozen)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def find_resource(rel):
    """Locate a bundled resource (PyInstaller _MEIPASS first, then app dir)."""
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.append(os.path.join(meipass, rel))
    candidates.append(os.path.join(base_dir(), rel))
    for cand in candidates:
        if cand and os.path.isfile(cand):
            return cand
    return None


def appdata_dir():
    """Per-user state directory (%APPDATA%\\WinExhale), always writable."""
    base = os.path.join(os.environ.get("APPDATA", base_dir()), APP_NAME)
    os.makedirs(base, exist_ok=True)
    return base


CONFIG_PATH = os.path.join(appdata_dir(), "winexhale_config.json")


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        pass
    legacy = os.path.join(base_dir(), "config.json")     # WinPurify-era config
    try:
        with open(legacy, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False

# --------------------------------------------------------- startup manager --

RUN_KEY_HKCU = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_KEY_HKLM = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
DISABLED_SUBKEY = "WinExhale_Disabled"
STARTUP_FOLDER = os.path.join(
    os.environ.get("APPDATA", ""),
    r"Microsoft\Windows\Start Menu\Programs\Startup")
BACKUP_DIR = os.path.join(appdata_dir(), "StartupBackup")
BACKUP_INDEX_PATH = os.path.join(appdata_dir(), "startup_backups.json")
FOLDER_EXTS = (".lnk", ".exe", ".bat", ".cmd", ".vbs", ".js", ".ps1", ".com")

# ------------------------------------------------------------- elevation ----

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def relaunch_elevated():
    """Relaunch the current process with a UAC 'runas' prompt."""
    if getattr(sys, "frozen", False):
        target = sys.executable
        params = subprocess.list2cmdline(sys.argv[1:])
    else:
        target = sys.executable
        params = subprocess.list2cmdline([os.path.abspath(__file__)] + list(sys.argv[1:]))
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", target, params, base_dir(), 1)
        return rc > 32
    except Exception:
        return False

# ------------------------------------------------------------ subprocess -----

def run_powershell(script, timeout=600):
    """Run a PowerShell snippet, return (returncode, merged_output)."""
    cmd = ["powershell", "-NoProfile", "-NonInteractive",
           "-ExecutionPolicy", "Bypass", "-Command", script]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              creationflags=CREATE_NO_WINDOW)
        out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        return 124, "Timeout"
    except OSError as exc:
        return 1, str(exc)


def run_simple(args, timeout=120):
    """Run an external command (reg/powercfg/ipconfig...), return (rc, output)."""
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                              creationflags=CREATE_NO_WINDOW)
        out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        return 124, "Timeout"
    except OSError as exc:
        return 1, str(exc)


def fmt_bytes(num):
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024.0 or unit == "TB":
            return f"{int(num)} B" if unit == "B" else f"{num:,.1f} {unit}"
        num /= 1024.0

# --------------------------------------------------------- translations -----

TRANSLATIONS = {
    "en": {
        "subtitle": "Windows Debloater, Privacy & Performance Suite",
        "lang_label": "Language",
        "btn_restore_point": "Create System Restore Point",
        "console_title": "Live Console",
        "btn_clear": "Clear",
        "tab_debloat": "Debloat",
        "tab_privacy": "Privacy",
        "tab_perf": "Performance",
        "tab_clean": "Junk Cleaner",
        "debloat_desc": "Select the preinstalled applications you want to remove, then click the button. "
                        "UWP apps are removed for the current user.",
        "btn_select_all": "Select all",
        "btn_deselect_all": "Deselect all",
        "btn_apply_debloat": "Remove selected apps",
        "privacy_desc": "Apply safe, reversible privacy tweaks to reduce telemetry and data collection. "
                        "A System Restore point can revert everything.",
        "btn_apply_privacy": "Apply privacy settings",
        "perf_desc": "One-click optimizations: disable unneeded background services and switch to the "
                     "High Performance power plan. 'Restore defaults' reverts these changes.",
        "switch_sysmain": "Disable SysMain (Superfetch)",
        "switch_wsearch": "Disable search indexing",
        "switch_powerplan": "High Performance power plan",
        "btn_apply_perf": "Optimize now",
        "btn_restore_perf": "Restore defaults",
        "clean_desc": "Clean temporary files, the DNS cache and GPU shader caches. "
                      "Locked files are skipped automatically.",
        "switch_user_temp": "User temporary files",
        "switch_win_temp": "Windows temporary files",
        "switch_dns": "Flush DNS cache",
        "switch_shader": "DirectX / GPU shader caches",
        "btn_clean": "Clean now",
        "label_freed": "Freed: {size}",
        "clean_user_temp": "user temp",
        "clean_win_temp": "Windows temp",
        "clean_shader": "shader caches",
        "tab_startup": "Startup",
        "startup_desc": "Manage the programs that start automatically with Windows. Disabling an item moves it to a "
                        "safe backup (the Run\\WinExhale_Disabled registry subkey, or the WinExhale backup folder) "
                        "so it can always be re-enabled.",
        "btn_refresh": "Refresh list",
        "startup_status": "{n} item(s), {d} disabled",
        "startup_empty": "No startup items found.",
        "src_folder": "Folder",
        "log_startup_scan": "Scanning startup entries...",
        "log_startup_scan_done": "Found {n} startup item(s).",
        "log_startup_disable": "Disabled: {name} ({source}) — backed up safely.",
        "log_startup_enable": "Enabled: {name} ({source})",
        "log_startup_err": "Failed: {name} — {err}",
        "log_welcome": "Welcome to {app} v{v} — running with administrator privileges. "
                       "It is recommended to create a restore point before making changes.",
        "log_lang_changed": "Language switched. Interface rebuilt.",
        "log_busy": "A task is already running — please wait for it to finish.",
        "log_none_selected": "Nothing is selected.",
        "log_rp_start": "Creating system restore point (can take up to a minute)...",
        "log_rp_ok": "System restore point created.",
        "log_rp_err": "Restore point failed: {err}",
        "log_deb_start": "Removing {n} selected app(s)...",
        "log_deb_removed": "Removed: {name}",
        "log_deb_notfound": "Not installed: {name}",
        "log_deb_partial": "Partially removed: {name} ({n} package(s) remain)",
        "log_deb_done": "Debloat complete.",
        "log_priv_start": "Applying {n} privacy setting(s)...",
        "log_reg_ok": "Registry: {key} -> {value} = {data}",
        "log_reg_err": "Registry failed ({key}\\{value}): {err}",
        "log_svc_ok": "Service configured: {name}",
        "log_svc_err": "Service failed ({name}): {err}",
        "log_priv_done": "Privacy settings applied.",
        "log_perf_start": "Applying performance optimizations...",
        "log_perf_restore": "Restoring default performance settings...",
        "log_pp_high": "Power plan set to High Performance.",
        "log_pp_balanced": "Power plan set to Balanced.",
        "log_pp_err": "Could not change the power plan.",
        "log_perf_done": "Performance optimizations applied.",
        "log_perf_restored": "Defaults restored.",
        "log_clean_start": "Scanning and cleaning selected targets...",
        "log_clean_target": "Cleaning {name}...",
        "log_clean_result": "{path} -> {size} freed ({files} files deleted, {failed} skipped)",
        "log_shader_none": "No shader caches found.",
        "log_dns_ok": "DNS cache flushed.",
        "log_clean_done": "Cleanup finished — total freed: {size}",
        "log_task_error": "Task error: {err}",
        "log_done": "Task finished.",
    },
    "fr": {
        "subtitle": "Suite de déblocage, confidentialité et performance pour Windows",
        "lang_label": "Langue",
        "btn_restore_point": "Créer un point de restauration",
        "console_title": "Journal en direct",
        "btn_clear": "Effacer",
        "tab_debloat": "Débloater",
        "tab_privacy": "Confidentialité",
        "tab_perf": "Performance",
        "tab_clean": "Nettoyage",
        "debloat_desc": "Sélectionnez les applications préinstallées à supprimer, puis cliquez sur le bouton. "
                        "Les applications UWP sont retirées pour l'utilisateur actuel.",
        "btn_select_all": "Tout sélectionner",
        "btn_deselect_all": "Tout désélectionner",
        "btn_apply_debloat": "Supprimer les apps sélectionnées",
        "privacy_desc": "Applique des réglages sûrs et réversibles pour réduire la télémétrie. "
                        "Un point de restauration permet de tout annuler.",
        "btn_apply_privacy": "Appliquer les réglages",
        "perf_desc": "Optimisation en un clic : désactive les services inutiles en arrière-plan et active le plan "
                     "d'alimentation Haute performance. « Rétablir les défauts » annule ces changements.",
        "switch_sysmain": "Désactiver SysMain (Superfetch)",
        "switch_wsearch": "Désactiver l'indexation de la recherche",
        "switch_powerplan": "Plan d'alimentation Haute performance",
        "btn_apply_perf": "Optimiser maintenant",
        "btn_restore_perf": "Rétablir les défauts",
        "clean_desc": "Nettoie les fichiers temporaires, le cache DNS et les caches de shaders GPU. "
                      "Les fichiers verrouillés sont ignorés automatiquement.",
        "switch_user_temp": "Fichiers temporaires utilisateur",
        "switch_win_temp": "Fichiers temporaires de Windows",
        "switch_dns": "Vider le cache DNS",
        "switch_shader": "Caches de shaders DirectX / GPU",
        "btn_clean": "Nettoyer maintenant",
        "label_freed": "Libéré : {size}",
        "clean_user_temp": "temp utilisateur",
        "clean_win_temp": "temp Windows",
        "clean_shader": "caches de shaders",
        "tab_startup": "Démarrage",
        "startup_desc": "Gérez les programmes lancés automatiquement avec Windows. La désactivation déplace "
                        "l'élément vers une sauvegarde sûre (sous-clé de registre Run\\WinExhale_Disabled ou "
                        "dossier de sauvegarde WinExhale) pour pouvoir le réactiver à tout moment.",
        "btn_refresh": "Actualiser la liste",
        "startup_status": "{n} élément(s), {d} désactivé(s)",
        "startup_empty": "Aucun élément de démarrage trouvé.",
        "src_folder": "Dossier",
        "log_startup_scan": "Analyse des programmes au démarrage...",
        "log_startup_scan_done": "{n} élément(s) de démarrage trouvé(s).",
        "log_startup_disable": "Désactivé : {name} ({source}) — sauvegardé en sécurité.",
        "log_startup_enable": "Activé : {name} ({source})",
        "log_startup_err": "Échec : {name} — {err}",
        "log_welcome": "Bienvenue dans {app} v{v} — exécution avec privilèges administrateur. "
                       "Il est recommandé de créer un point de restauration avant toute modification.",
        "log_lang_changed": "Langue changée. Interface reconstruite.",
        "log_busy": "Une tâche est déjà en cours — veuillez attendre la fin.",
        "log_none_selected": "Aucune sélection.",
        "log_rp_start": "Création du point de restauration (peut prendre une minute)...",
        "log_rp_ok": "Point de restauration créé.",
        "log_rp_err": "Échec du point de restauration : {err}",
        "log_deb_start": "Suppression de {n} application(s)...",
        "log_deb_removed": "Supprimé : {name}",
        "log_deb_notfound": "Non installé : {name}",
        "log_deb_partial": "Suppression partielle : {name} ({n} paquet(s) restant(s))",
        "log_deb_done": "Déblocage terminé.",
        "log_priv_start": "Application de {n} réglage(s)...",
        "log_reg_ok": "Registre : {key} -> {value} = {data}",
        "log_reg_err": "Échec registre ({key}\\{value}) : {err}",
        "log_svc_ok": "Service configuré : {name}",
        "log_svc_err": "Échec service ({name}) : {err}",
        "log_priv_done": "Réglages de confidentialité appliqués.",
        "log_perf_start": "Application des optimisations...",
        "log_perf_restore": "Rétablissement des réglages par défaut...",
        "log_pp_high": "Plan haute performance activé.",
        "log_pp_balanced": "Plan équilibré rétabli.",
        "log_pp_err": "Impossible de changer de plan d'alimentation.",
        "log_perf_done": "Optimisations appliquées.",
        "log_perf_restored": "Défauts rétablis.",
        "log_clean_start": "Analyse et nettoyage des cibles sélectionnées...",
        "log_clean_target": "Nettoyage de {name}...",
        "log_clean_result": "{path} -> {size} libérés ({files} fichiers supprimés, {failed} ignorés)",
        "log_shader_none": "Aucun cache de shaders trouvé.",
        "log_dns_ok": "Cache DNS vidé.",
        "log_clean_done": "Nettoyage terminé — total libéré : {size}",
        "log_task_error": "Erreur de tâche : {err}",
        "log_done": "Tâche terminée.",
    },
}

# ------------------------------------------------------------------ data ----

# {"en": display, "fr": display, "pattern": Appx package name pattern}
BLOAT_APPS = [
    {"en": "Cortana",                        "fr": "Cortana",                            "pattern": "Microsoft.549981C3F5F10"},
    {"en": "Bing News",                      "fr": "Actualités Bing",                    "pattern": "Microsoft.BingNews"},
    {"en": "Bing Weather",                   "fr": "Météo Bing",                         "pattern": "Microsoft.BingWeather"},
    {"en": "Feedback Hub",                   "fr": "Hub de commentaires",                "pattern": "Microsoft.WindowsFeedbackHub"},
    {"en": "Get Help",                       "fr": "Obtenir de l'aide",                  "pattern": "Microsoft.GetHelp"},
    {"en": "Tips (Get Started)",             "fr": "Astuces (Prise en main)",            "pattern": "Microsoft.Getstarted"},
    {"en": "Office Hub (Get Office)",        "fr": "Hub Office",                         "pattern": "Microsoft.MicrosoftOfficeHub"},
    {"en": "Xbox Console Companion",         "fr": "Compagnon Xbox",                     "pattern": "Microsoft.XboxApp"},
    {"en": "Xbox Game Bar (Win+G)",          "fr": "Barre de jeu Xbox (Win+G)",          "pattern": "Microsoft.XboxGamingOverlay"},
    {"en": "Xbox Speech-to-Text Overlay",    "fr": "Superposition vocale Xbox",          "pattern": "Microsoft.XboxSpeechToTextOverlay"},
    {"en": "Solitaire Collection",           "fr": "Solitaire Microsoft",                "pattern": "Microsoft.MicrosoftSolitaireCollection"},
    {"en": "3D Viewer",                      "fr": "Visionneuse 3D",                     "pattern": "Microsoft.Microsoft3DViewer"},
    {"en": "Print 3D",                       "fr": "Print 3D",                           "pattern": "Microsoft.Print3D"},
    {"en": "Candy Crush Saga",               "fr": "Candy Crush Saga",                   "pattern": "king.com.CandyCrushSaga"},
    {"en": "Candy Crush Soda Saga",          "fr": "Candy Crush Soda Saga",              "pattern": "king.com.CandyCrushSodaSaga"},
    {"en": "Bubble Witch 3 Saga",            "fr": "Bubble Witch 3 Saga",                "pattern": "king.com.BubbleWitch3Saga"},
    {"en": "Skype",                          "fr": "Skype",                              "pattern": "Microsoft.SkypeApp"},
    {"en": "Spotify",                        "fr": "Spotify",                            "pattern": "SpotifyAB.SpotifyMusic"},
    {"en": "Microsoft Teams (personal)",     "fr": "Microsoft Teams (personnel)",        "pattern": "MSTeams"},
    {"en": "Clipchamp",                      "fr": "Clipchamp",                          "pattern": "Clipchamp.Clipchamp"},
    {"en": "Your Phone",                     "fr": "Votre téléphone (Your Phone)",       "pattern": "Microsoft.YourPhone"},
]

PRIVACY_ITEMS = [
    {
        "key": "diagtrack",
        "title": {"en": "Disable the Diagnostics Tracking service (DiagTrack)",
                  "fr": "Désactiver le service de suivi de diagnostic (DiagTrack)"},
        "desc": {"en": "Stops the Connected User Experiences and Telemetry service.",
                 "fr": "Arrête le service « Expériences des utilisateurs connectés et télémétrie »."},
        "service": "DiagTrack",
    },
    {
        "key": "dmwappush",
        "title": {"en": "Disable the WAP Push service (dmwappushservice)",
                  "fr": "Désactiver le service WAP Push (dmwappushservice)"},
        "desc": {"en": "Legacy device-management channel, unused on most PCs.",
                 "fr": "Canal de gestion hérité, inutilisé sur la plupart des PC."},
        "service": "dmwappushservice",
    },
    {
        "key": "adid",
        "title": {"en": "Disable the Advertising ID",
                  "fr": "Désactiver l'identifiant publicitaire"},
        "desc": {"en": "Prevents apps from using a unique ID for personalized ads.",
                 "fr": "Empêche les apps d'utiliser un identifiant unique pour les publicités personnalisées."},
        "regs": [
            (r"HKCU\Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", "REG_DWORD", "0"),
            (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\AdvertisingInfo", "DisabledByPolicy", "REG_DWORD", "1"),
        ],
    },
    {
        "key": "wer",
        "title": {"en": "Disable Windows Error Reporting",
                  "fr": "Désactiver le rapport d'erreurs Windows"},
        "desc": {"en": "Stops crash reports from being sent to Microsoft.",
                 "fr": "Empêche l'envoi des rapports de plantage à Microsoft."},
        "regs": [
            (r"HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting", "Disabled", "REG_DWORD", "1"),
            (r"HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting", "DontShowUI", "REG_DWORD", "1"),
        ],
    },
    {
        "key": "cortana",
        "title": {"en": "Disable Cortana and cloud search",
                  "fr": "Désactiver Cortana et la recherche cloud"},
        "desc": {"en": "Disables Cortana policies and background cloud synchronization.",
                 "fr": "Désactive les stratégies Cortana et la synchronisation cloud en arrière-plan."},
        "regs": [
            (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\Windows Search", "AllowCortana", "REG_DWORD", "0"),
            (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\Windows Search", "AllowCloudSearch", "REG_DWORD", "0"),
            (r"HKCU\SOFTWARE\Microsoft\Personalization\Settings", "AcceptedPrivacyPolicy", "REG_DWORD", "0"),
        ],
    },
    {
        "key": "telemetry",
        "title": {"en": "Set diagnostic data to the minimum level",
                  "fr": "Données de diagnostic au niveau minimal"},
        "desc": {"en": "Sets AllowTelemetry to Basic (required data only).",
                 "fr": "Définit AllowTelemetry sur Basique (données requises uniquement)."},
        "regs": [
            (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", "REG_DWORD", "1"),
            (r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection", "AllowTelemetry", "REG_DWORD", "1"),
        ],
    },
]

# ------------------------------------------------------- script builders ----

def ps_remove_appx(pattern):
    p = pattern
    return (
        "$ErrorActionPreference = 'Continue'\n"
        f"$pkgs = Get-AppxPackage -Name '*{p}*' -ErrorAction SilentlyContinue\n"
        "if (-not $pkgs) { Write-Output 'RESULT_NOT_FOUND'; exit 0 }\n"
        "$pkgs | Remove-AppxPackage -ErrorAction Continue\n"
        f"$remaining = @(Get-AppxPackage -Name '*{p}*' -ErrorAction SilentlyContinue).Count\n"
        "if ($remaining -eq 0) { Write-Output 'RESULT_REMOVED' }\n"
        "else { Write-Output ('RESULT_PARTIAL:' + $remaining) }\n"
    )


def ps_service(name, disable=True):
    startup = "Disabled" if disable else "Automatic"
    stop_line = f"try {{ Stop-Service -Name '{name}' -Force -ErrorAction SilentlyContinue }} catch {{}}\n"
    start_line = f"try {{ Start-Service -Name '{name}' -ErrorAction SilentlyContinue }} catch {{}}\n"
    return (
        (stop_line if disable else "")
        + f"try {{ Set-Service -Name '{name}' -StartupType {startup} -ErrorAction Stop; "
        f"Write-Output 'SVC_OK:{name}' }}\n"
        f"catch {{ Write-Output ('SVC_ERR:{name}:' + $_.Exception.Message) }}\n"
        + ("" if disable else start_line)
    )


def ps_restore_point():
    return (
        "$ErrorActionPreference = 'Stop'\n"
        "try {\n"
        "    Enable-ComputerRestore -Drive ($env:SystemDrive + '\\') -ErrorAction SilentlyContinue\n"
        "    Checkpoint-Computer -Description 'WinExhale restore point' -RestorePointType 'MODIFY_SETTINGS'\n"
        "    Write-Output 'RP_OK'\n"
        "} catch { Write-Output ('RP_ERR:' + $_.Exception.Message) }\n"
    )

# ------------------------------------------------------------- cleaning -----

def clean_directory(path):
    """Delete everything inside a directory; return (freed_bytes, removed, failed)."""
    freed = removed = failed = 0
    if not os.path.isdir(path):
        return freed, removed, failed
    for dirpath, _dirnames, filenames in os.walk(path):
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                size = os.path.getsize(fpath)
                os.remove(fpath)
                freed += size
                removed += 1
            except OSError:
                failed += 1
    for dirpath, dirnames, _files in os.walk(path, topdown=False):
        for dname in dirnames:                       # sweep now-empty subfolders
            try:
                os.rmdir(os.path.join(dirpath, dname))
            except OSError:
                pass
    return freed, removed, failed


def shader_cache_dirs():
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return []
    candidates = [
        os.path.join(local, "D3DSCache"),
        os.path.join(local, "NVIDIA", "DXCache"),
        os.path.join(local, "NVIDIA", "GLCache"),
        os.path.join(local, "AMD", "DxCache"),
        os.path.join(local, "Intel", "ShaderCache"),
    ]
    return [c for c in candidates if os.path.isdir(c)]

# ---------------------------------------------------- startup logic ---------

def load_backup_index():
    try:
        with open(BACKUP_INDEX_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_backup_index(entries):
    try:
        with open(BACKUP_INDEX_PATH, "w", encoding="utf-8") as fh:
            json.dump(entries, fh, indent=2)
    except OSError:
        pass


def scan_startup_items():
    """Collect autorun entries from the HKCU/HKLM Run keys and the startup
    folder. Disabled registry values live in Run\\WinExhale_Disabled and
    disabled folder files in the WinExhale backup folder; both are reported
    so the user can re-enable them."""
    items = []
    hives = (
        ("HKCU", winreg.HKEY_CURRENT_USER, RUN_KEY_HKCU),
        ("HKLM", winreg.HKEY_LOCAL_MACHINE, RUN_KEY_HKLM),
    )
    for label, root, subkey in hives:
        for path, disabled in ((subkey, False),
                               (subkey + "\\" + DISABLED_SUBKEY, True)):
            try:
                key = winreg.OpenKey(root, path)
            except OSError:
                continue
            with key:
                for i in range(winreg.QueryInfoKey(key)[1]):
                    try:
                        name, data, vtype = winreg.EnumValue(key, i)
                    except OSError:
                        continue
                    if isinstance(data, str):
                        items.append({"source": label, "name": name,
                                      "command": data, "vtype": vtype,
                                      "disabled": disabled})
    if os.path.isdir(STARTUP_FOLDER):
        for fname in sorted(os.listdir(STARTUP_FOLDER)):
            fpath = os.path.join(STARTUP_FOLDER, fname)
            if os.path.isfile(fpath) and fname.lower().endswith(FOLDER_EXTS):
                items.append({"source": "Folder", "name": fname,
                              "command": fpath, "vtype": None,
                              "disabled": False})
    for entry in load_backup_index():
        backup_path = os.path.join(BACKUP_DIR, entry.get("file", ""))
        if os.path.isfile(backup_path):
            items.append({"source": "Folder", "name": entry["file"],
                          "command": entry.get("from", backup_path),
                          "vtype": None, "disabled": True})
    return items


def startup_toggle_registry(item, disable):
    """Move a Run value to/from the WinExhale_Disabled backup subkey,
    preserving its original type (REG_SZ / REG_EXPAND_SZ)."""
    root = (winreg.HKEY_CURRENT_USER if item["source"] == "HKCU"
            else winreg.HKEY_LOCAL_MACHINE)
    subkey = RUN_KEY_HKCU if item["source"] == "HKCU" else RUN_KEY_HKLM
    src_path = subkey + "\\" + DISABLED_SUBKEY if item["disabled"] else subkey
    dst_path = subkey if item["disabled"] else subkey + "\\" + DISABLED_SUBKEY
    with winreg.OpenKey(root, src_path, 0, winreg.KEY_READ) as src:
        data, vtype = winreg.QueryValueEx(src, item["name"])
    with winreg.CreateKeyEx(root, dst_path, 0, winreg.KEY_SET_VALUE) as dst:
        winreg.SetValueEx(dst, item["name"], 0, vtype, data)
    with winreg.OpenKey(root, src_path, 0, winreg.KEY_SET_VALUE) as src:
        winreg.DeleteValue(src, item["name"])


def startup_toggle_folder(item, disable):
    """Move a startup-folder file to/from the WinExhale backup folder."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    index = load_backup_index()
    if disable:
        src = os.path.join(STARTUP_FOLDER, item["name"])
        dst = os.path.join(BACKUP_DIR, item["name"])
        counter = 1
        while os.path.exists(dst):                     # never overwrite backups
            stem, ext = os.path.splitext(item["name"])
            dst = os.path.join(BACKUP_DIR, f"{stem}_{counter}{ext}")
            counter += 1
        shutil.move(src, dst)
        index.append({"file": os.path.basename(dst), "from": src})
    else:
        entry = next((e for e in index if e.get("file") == item["name"]), None)
        if entry is None:
            raise FileNotFoundError(item["name"])
        src = os.path.join(BACKUP_DIR, entry["file"])
        dst = entry.get("from") or os.path.join(STARTUP_FOLDER, entry["file"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        index.remove(entry)
    save_backup_index(index)

# ------------------------------------------------------------------- app ----

class WinExhaleApp(ctk.CTk):

    def __init__(self):
        super().__init__(fg_color=COL_BG)
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1100x780")
        self.minsize(980, 700)

        icon_path = find_resource("app_icon.ico")
        if icon_path:
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self.cfg = load_config()
        self.lang = self.cfg.get("language")
        if self.lang not in ("en", "fr"):
            self.lang = None

        self.busy = False
        self._busy_widgets = []
        self._log_queue = queue.Queue()
        self.header = None
        self.tab_area = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_console()
        self.after(100, self._poll_log_queue)
        if self.lang is None:
            # Defer the language modal until the event loop is running; a
            # Toplevel + grab created before mainloop is unreliable on Windows.
            self.after(150, self._startup_language_flow)
        else:
            self.rebuild_ui()
        self.log(self.t("log_welcome", app=APP_NAME, v=APP_VERSION), "success")

    # --------------------------------------------------------- helpers ----

    def t(self, key, **fmt):
        table = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"])
        text = table.get(key) or TRANSLATIONS["en"].get(key) or key
        return text.format(**fmt) if fmt else text

    def _post(self, fn):
        """Schedule a UI update from a worker thread."""
        try:
            self.after(0, fn)
        except RuntimeError:
            pass

    def log(self, message, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_queue.put((ts, message, level))

    def _poll_log_queue(self):
        try:
            while True:
                ts, msg, level = self._log_queue.get_nowait()
                self._append_log(ts, msg, level)
        except queue.Empty:
            pass
        try:
            if self.winfo_exists():
                self.after(100, self._poll_log_queue)
        except Exception:
            pass

    def _append_log(self, ts, msg, level):
        box = self.console
        box.configure(state="normal")
        box.insert("end", f"[{ts}] ", ("dim",))
        box.insert("end", msg.rstrip("\n") + "\n", (level,))
        box.see("end")
        box.configure(state="disabled")

    def _clear_console(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    def _run_task(self, fn, *args):
        """Run a system task on a background thread; UI stays responsive."""
        if self.busy:
            self.log(self.t("log_busy"), "warn")
            return
        self.busy = True
        self._set_busy_ui(True)

        def wrap():
            try:
                fn(*args)
            except Exception as exc:                       # keep the UI alive no matter what
                self.log(self.t("log_task_error", err=exc), "error")
            finally:
                self._post(self._task_finished)

        threading.Thread(target=wrap, daemon=True).start()

    def _task_finished(self):
        self.busy = False
        self._set_busy_ui(False)
        self.log(self.t("log_done"), "dim")

    def _set_busy_ui(self, disabled):
        state = "disabled" if disabled else "normal"
        widgets = list(self._busy_widgets) + list(getattr(self, "_startup_switches", []))
        for widget in widgets:
            try:
                widget.configure(state=state)
            except Exception:
                pass

    # ------------------------------------------------------ language ------

    def _ask_language(self):
        dlg = ctk.CTkToplevel(self, fg_color=COL_BG)
        dlg.title(f"{APP_NAME} — Language / Langue")
        dlg.attributes("-topmost", True)
        dlg.transient(self)
        dlg.resizable(False, False)
        self._lang_dlg = dlg
        self._lang_cancelled = False
        dlg.protocol("WM_DELETE_WINDOW", self._cancel_language)

        ctk.CTkLabel(dlg, text="Choose your language", font=(FONT_FAMILY, 19, "bold"),
                     text_color=COL_TEXT).pack(pady=(36, 2))
        ctk.CTkLabel(dlg, text="Choisissez votre langue", font=(FONT_FAMILY, 13),
                     text_color=COL_TEXT_DIM).pack(pady=(0, 20))
        ctk.CTkButton(dlg, text="English", width=280, height=44, corner_radius=10,
                      font=(FONT_FAMILY, 15, "bold"), fg_color=COL_ACCENT,
                      hover_color=COL_ACCENT_HOVER, text_color=COL_ON_ACCENT,
                      command=lambda: self._pick_language("en")).pack(pady=6)
        ctk.CTkButton(dlg, text="Français", width=280, height=44, corner_radius=10,
                      font=(FONT_FAMILY, 15, "bold"), fg_color=COL_CARD_2,
                      hover_color=COL_ACCENT_DARK, text_color=COL_TEXT,
                      command=lambda: self._pick_language("fr")).pack(pady=6)
        ctk.CTkLabel(dlg, text="You can change this later from the header — Modifiable plus tard.",
                     font=(FONT_FAMILY, 10), text_color=COL_TEXT_DIM).pack(pady=(16, 0))

        w, h = 470, 360
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        dlg.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")
        try:
            dlg.wait_visibility()
        except Exception:
            pass
        dlg.grab_set()
        self.wait_window(dlg)

    def _startup_language_flow(self):
        """Runs once the mainloop is live: show the picker, then build the UI."""
        try:
            self._ask_language()
        except Exception as exc:
            self.log(f"Language dialog error ({exc}) — defaulting to English.", "warn")
            if self.lang not in ("en", "fr"):
                self.lang = "en"
                self.cfg["language"] = "en"
                save_config(self.cfg)
        if self._lang_cancelled or self.lang not in ("en", "fr"):
            self.destroy()
            return
        self.rebuild_ui()

    def _pick_language(self, code):
        self.lang = code
        self.cfg["language"] = code
        save_config(self.cfg)
        if getattr(self, "_lang_dlg", None):
            self._lang_dlg.destroy()

    def _cancel_language(self):
        self._lang_cancelled = True
        if getattr(self, "_lang_dlg", None):
            self._lang_dlg.destroy()

    def _on_lang_change(self, choice):
        new = "en" if choice == "English" else "fr"
        if new == self.lang:
            return
        self.lang = new
        self.cfg["language"] = new
        save_config(self.cfg)
        self.rebuild_ui()
        self.log(self.t("log_lang_changed"), "info")

    # ---------------------------------------------------------- layout ----

    def rebuild_ui(self):
        if self.header:
            self.header.destroy()
        if self.tab_area:
            self.tab_area.destroy()
        self._busy_widgets = []
        self._build_header()
        self._build_tabs()
        self.console_label.configure(text=self.t("console_title"))
        self.console_clear_btn.configure(text=self.t("btn_clear"))

    def _load_logo(self):
        if Image is None:
            return None
        path = find_resource("app_logo.png")
        if not path:
            return None
        try:
            return ctk.CTkImage(light_image=Image.open(path), dark_image=Image.open(path),
                                size=(46, 46))
        except Exception:
            return None

    def _build_header(self):
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))

        logo = self._load_logo()
        if logo:
            self._logo_img = logo                     # keep a reference (Tk GC)
            ctk.CTkLabel(self.header, image=logo, text="").pack(side="left", padx=(6, 14))

        titles = ctk.CTkFrame(self.header, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(titles, text=APP_NAME, font=(FONT_FAMILY, 24, "bold"),
                     text_color=COL_TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(titles, text=self.t("subtitle"), font=(FONT_FAMILY, 12),
                     text_color=COL_TEXT_DIM, anchor="w").pack(anchor="w")

        right = ctk.CTkFrame(self.header, fg_color="transparent")
        right.pack(side="right", padx=(10, 6))
        ctk.CTkLabel(right, text=self.t("lang_label"), font=(FONT_FAMILY, 11),
                     text_color=COL_TEXT_DIM).pack(anchor="e")
        self.lang_menu = ctk.CTkOptionMenu(
            right, values=["English", "Français"], width=140, height=30,
            fg_color=COL_CARD_2, button_color=COL_ACCENT_DARK,
            button_hover_color=COL_ACCENT_HOVER, text_color=COL_TEXT,
            command=self._on_lang_change)
        self.lang_menu.set("English" if self.lang == "en" else "Français")
        self.lang_menu.pack(anchor="e", pady=(0, 8))
        self.rp_btn = ctk.CTkButton(
            right, text=self.t("btn_restore_point"), width=280, height=38, corner_radius=8,
            font=(FONT_FAMILY, 12, "bold"), fg_color=COL_ACCENT,
            hover_color=COL_ACCENT_HOVER, text_color=COL_ON_ACCENT,
            command=self.on_restore_point)
        self.rp_btn.pack(anchor="e")
        self._busy_widgets += [self.rp_btn, self.lang_menu]

    def _build_tabs(self):
        self.tab_area = ctk.CTkFrame(self, fg_color="transparent")
        self.tab_area.grid(row=1, column=0, sticky="nsew", padx=16, pady=(4, 2))
        self.tab_area.grid_rowconfigure(0, weight=1)
        self.tab_area.grid_columnconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(
            self.tab_area, fg_color=COL_CARD, corner_radius=12,
            segmented_button_selected_color=COL_ACCENT_DARK,
            segmented_button_selected_hover_color=COL_ACCENT_HOVER,
            segmented_button_unselected_color=COL_CARD_2,
            text_color=COL_TEXT)
        self.tabview.grid(row=0, column=0, sticky="nsew")

        for tab_key in ("tab_debloat", "tab_privacy", "tab_perf", "tab_startup", "tab_clean"):
            self.tabview.add(self.t(tab_key))

        self._build_debloat_tab(self.tabview.tab(self.t("tab_debloat")))
        self._build_privacy_tab(self.tabview.tab(self.t("tab_privacy")))
        self._build_perf_tab(self.tabview.tab(self.t("tab_perf")))
        self._build_startup_tab(self.tabview.tab(self.t("tab_startup")))
        self._build_clean_tab(self.tabview.tab(self.t("tab_clean")))

    def _build_console(self):
        frame = ctk.CTkFrame(self, fg_color=COL_CARD, corner_radius=12)
        frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 14))

        self.console_label = ctk.CTkLabel(frame, text="", font=(FONT_FAMILY, 12, "bold"),
                                          text_color=COL_TEXT_DIM)
        self.console_label.pack(side="left", padx=14, pady=(8, 0))
        self.console_clear_btn = ctk.CTkButton(
            frame, text="", width=80, height=26, corner_radius=6, fg_color=COL_CARD_2,
            hover_color=COL_ACCENT_DARK, text_color=COL_TEXT, command=self._clear_console)
        self.console_clear_btn.pack(side="right", padx=10, pady=(6, 0))

        self.console = ctk.CTkTextbox(frame, height=190, font=(FONT_MONO, 11),
                                      fg_color=COL_CONSOLE_BG, text_color=COL_TEXT,
                                      wrap="word", border_width=0)
        self.console.pack(fill="both", expand=True, padx=10, pady=(6, 10))
        for tag, color in (("info", COL_TEXT), ("dim", COL_TEXT_DIM), ("success", COL_SUCCESS),
                           ("warn", COL_WARN), ("error", COL_ERROR), ("raw", "#6B7F9E")):
            try:
                self.console.tag_config(tag, foreground=color)
            except Exception:
                pass
        self.console.configure(state="disabled")

    # ------------------------------------------------------ tab: debloat ---

    def _build_debloat_tab(self, tab):
        ctk.CTkLabel(tab, text=self.t("debloat_desc"), font=(FONT_FAMILY, 11),
                     text_color=COL_TEXT_DIM, wraplength=900, justify="left",
                     anchor="w").pack(anchor="w", padx=16, pady=(10, 4))

        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=4)
        ctk.CTkButton(bar, text=self.t("btn_select_all"), width=130, height=30, corner_radius=6,
                      fg_color=COL_CARD_2, hover_color=COL_ACCENT_DARK, text_color=COL_TEXT,
                      command=self._select_all_debloat).pack(side="left")
        ctk.CTkButton(bar, text=self.t("btn_deselect_all"), width=130, height=30, corner_radius=6,
                      fg_color=COL_CARD_2, hover_color=COL_ACCENT_DARK, text_color=COL_TEXT,
                      command=self._deselect_all_debloat).pack(side="left", padx=8)
        btn = ctk.CTkButton(bar, text=self.t("btn_apply_debloat"), width=240, height=34,
                            corner_radius=8, font=(FONT_FAMILY, 12, "bold"),
                            fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER,
                            text_color=COL_ON_ACCENT, command=self.on_debloat)
        btn.pack(side="right")
        self._busy_widgets.append(btn)

        scroll = ctk.CTkScrollableFrame(tab, fg_color=COL_CARD_2)
        scroll.pack(fill="both", expand=True, padx=16, pady=(4, 12))

        self._debloat_vars = []
        for app in BLOAT_APPS:
            var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(scroll, text=app[self.lang], variable=var,
                            font=(FONT_FAMILY, 12), fg_color=COL_ACCENT,
                            hover_color=COL_ACCENT_HOVER, checkmark_color=COL_ON_ACCENT,
                            border_color=COL_TEXT_DIM).pack(anchor="w", padx=10, pady=3, fill="x")
            self._debloat_vars.append((app, var))

    def _select_all_debloat(self):
        for _app, var in self._debloat_vars:
            var.set(True)

    def _deselect_all_debloat(self):
        for _app, var in self._debloat_vars:
            var.set(False)

    def on_debloat(self):
        selected = [(app, var) for app, var in self._debloat_vars if var.get()]
        if not selected:
            self.log(self.t("log_none_selected"), "warn")
            return
        self._run_task(self._task_debloat, selected)

    def _task_debloat(self, selected):
        self.log(self.t("log_deb_start", n=len(selected)), "info")
        for app, _var in selected:
            name = app[self.lang]
            _rc, out = run_powershell(ps_remove_appx(app["pattern"]), timeout=300)
            status = ""
            for line in (l.strip() for l in out.splitlines()):
                if line.startswith("RESULT_"):
                    status = line
                elif line:
                    self.log(f"  {name}: {line}", "raw")
            if status.startswith("RESULT_REMOVED"):
                self.log(self.t("log_deb_removed", name=name), "success")
            elif status.startswith("RESULT_NOT_FOUND"):
                self.log(self.t("log_deb_notfound", name=name), "dim")
            else:
                remaining = status.split(":", 1)[1] if ":" in status else "?"
                self.log(self.t("log_deb_partial", name=name, n=remaining), "warn")
        self.log(self.t("log_deb_done"), "success")

    # ------------------------------------------------------ tab: privacy ---

    def _build_privacy_tab(self, tab):
        ctk.CTkLabel(tab, text=self.t("privacy_desc"), font=(FONT_FAMILY, 11),
                     text_color=COL_TEXT_DIM, wraplength=900, justify="left",
                     anchor="w").pack(anchor="w", padx=16, pady=(10, 4))
        btn = ctk.CTkButton(tab, text=self.t("btn_apply_privacy"), width=240, height=34,
                            corner_radius=8, font=(FONT_FAMILY, 12, "bold"),
                            fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER,
                            text_color=COL_ON_ACCENT, command=self.on_privacy)
        btn.pack(anchor="e", padx=16, pady=4)
        self._busy_widgets.append(btn)

        scroll = ctk.CTkScrollableFrame(tab, fg_color=COL_CARD_2)
        scroll.pack(fill="both", expand=True, padx=16, pady=(4, 12))

        self._privacy_vars = []
        for item in PRIVACY_ITEMS:
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=7)
            texts = ctk.CTkFrame(row, fg_color="transparent")
            texts.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(texts, text=item["title"][self.lang],
                         font=(FONT_FAMILY, 12, "bold"), text_color=COL_TEXT,
                         anchor="w").pack(anchor="w")
            ctk.CTkLabel(texts, text=item["desc"][self.lang], font=(FONT_FAMILY, 11),
                         text_color=COL_TEXT_DIM, anchor="w", wraplength=660,
                         justify="left").pack(anchor="w")
            var = ctk.BooleanVar(value=False)
            ctk.CTkSwitch(row, text="", variable=var, width=56,
                          progress_color=COL_ACCENT).pack(side="right", padx=(10, 4))
            self._privacy_vars.append((item, var))

    def on_privacy(self):
        selected = [(item, var) for item, var in self._privacy_vars if var.get()]
        if not selected:
            self.log(self.t("log_none_selected"), "warn")
            return
        self._run_task(self._task_privacy, selected)

    def _log_service_output(self, out):
        for line in (l.strip() for l in out.splitlines()):
            if not line:
                continue
            if line.startswith("SVC_OK:"):
                self.log(self.t("log_svc_ok", name=line.split(":", 1)[1]), "info")
            elif line.startswith("SVC_ERR:"):
                parts = line.split(":", 2)
                name = parts[1] if len(parts) > 2 else "?"
                err = parts[2] if len(parts) > 2 else line
                self.log(self.t("log_svc_err", name=name, err=err), "error")
            else:
                self.log(line, "raw")

    def _task_privacy(self, selected):
        self.log(self.t("log_priv_start", n=len(selected)), "info")
        for item, _var in selected:
            if item.get("service"):
                _rc, out = run_powershell(ps_service(item["service"], disable=True))
                self._log_service_output(out)
            for key, value, rtype, data in item.get("regs", []):
                rc, out = run_simple(["reg", "add", key, "/v", value, "/t", rtype, "/d", data, "/f"])
                if rc == 0:
                    self.log(self.t("log_reg_ok", key=key, value=value, data=data), "info")
                else:
                    err = (out or f"exit code {rc}").strip()
                    self.log(self.t("log_reg_err", key=key, value=value, err=err), "error")
        self.log(self.t("log_priv_done"), "success")

    # ---------------------------------------------------------- tab: perf ---

    def _build_perf_tab(self, tab):
        ctk.CTkLabel(tab, text=self.t("perf_desc"), font=(FONT_FAMILY, 11),
                     text_color=COL_TEXT_DIM, wraplength=900, justify="left",
                     anchor="w").pack(anchor="w", padx=16, pady=(10, 4))

        body = ctk.CTkFrame(tab, fg_color=COL_CARD_2)
        body.pack(fill="both", expand=True, padx=16, pady=(4, 6))

        self._perf_vars = []
        rows = (
            ("switch_sysmain", "sysmain"),
            ("switch_wsearch", "wsearch"),
            ("switch_powerplan", "power"),
        )
        for label_key, var_key in rows:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=10)
            ctk.CTkLabel(row, text=self.t(label_key), font=(FONT_FAMILY, 13, "bold"),
                         text_color=COL_TEXT, anchor="w").pack(side="left")
            var = ctk.BooleanVar(value=True)
            ctk.CTkSwitch(row, text="", variable=var, width=56,
                          progress_color=COL_ACCENT).pack(side="right")
            self._perf_vars.append((var_key, var))

        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(2, 12))
        btn = ctk.CTkButton(bar, text=self.t("btn_apply_perf"), width=220, height=36,
                            corner_radius=8, font=(FONT_FAMILY, 12, "bold"),
                            fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER,
                            text_color=COL_ON_ACCENT, command=self.on_perf)
        btn.pack(side="right")
        rbtn = ctk.CTkButton(bar, text=self.t("btn_restore_perf"), width=180, height=36,
                             corner_radius=8, fg_color=COL_CARD_2,
                             hover_color=COL_ACCENT_DARK, text_color=COL_TEXT,
                             command=self.on_perf_restore)
        rbtn.pack(side="right", padx=8)
        self._busy_widgets += [btn, rbtn]

    def on_perf(self):
        keys = [key for key, var in self._perf_vars if var.get()]
        if not keys:
            self.log(self.t("log_none_selected"), "warn")
            return
        self._run_task(self._task_perf, keys, False)

    def on_perf_restore(self):
        self._run_task(self._task_perf, ["sysmain", "wsearch", "power"], True)

    def _set_power_plan(self, guid):
        rc, _out = run_simple(["powercfg", "/setactive", guid])
        if rc == 0:
            return True
        # The High Performance scheme can be absent on some OEM images: recreate it.
        _rc2, out2 = run_simple(["powercfg", "-duplicatescheme", guid])
        match = re.search(r"GUID:\s*([0-9a-fA-F]{8}-[0-9a-fA-F-]+)", out2 or "")
        if match:
            rc3, _out3 = run_simple(["powercfg", "/setactive", match.group(1)])
            return rc3 == 0
        return False

    def _task_perf(self, keys, restore):
        self.log(self.t("log_perf_restore" if restore else "log_perf_start"), "info")
        if "sysmain" in keys:
            _rc, out = run_powershell(ps_service("SysMain", disable=not restore))
            self._log_service_output(out)
        if "wsearch" in keys:
            _rc, out = run_powershell(ps_service("WSearch", disable=not restore))
            self._log_service_output(out)
        if "power" in keys:
            guid = BALANCED_GUID if restore else HIGH_PERF_GUID
            if self._set_power_plan(guid):
                self.log(self.t("log_pp_balanced" if restore else "log_pp_high"), "success")
            else:
                self.log(self.t("log_pp_err"), "error")
        self.log(self.t("log_perf_restored" if restore else "log_perf_done"), "success")

    # --------------------------------------------------------- tab: clean ---

    def _build_clean_tab(self, tab):
        ctk.CTkLabel(tab, text=self.t("clean_desc"), font=(FONT_FAMILY, 11),
                     text_color=COL_TEXT_DIM, wraplength=900, justify="left",
                     anchor="w").pack(anchor="w", padx=16, pady=(10, 4))

        body = ctk.CTkFrame(tab, fg_color=COL_CARD_2)
        body.pack(fill="both", expand=True, padx=16, pady=(4, 6))

        self._clean_vars = []
        rows = (
            ("switch_user_temp", "user_temp"),
            ("switch_win_temp", "win_temp"),
            ("switch_dns", "dns"),
            ("switch_shader", "shader"),
        )
        for label_key, var_key in rows:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=8)
            ctk.CTkLabel(row, text=self.t(label_key), font=(FONT_FAMILY, 13, "bold"),
                         text_color=COL_TEXT, anchor="w").pack(side="left")
            var = ctk.BooleanVar(value=True)
            ctk.CTkSwitch(row, text="", variable=var, width=56,
                          progress_color=COL_ACCENT).pack(side="right")
            self._clean_vars.append((var_key, var))

        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(2, 12))
        btn = ctk.CTkButton(bar, text=self.t("btn_clean"), width=220, height=36,
                            corner_radius=8, font=(FONT_FAMILY, 12, "bold"),
                            fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER,
                            text_color=COL_ON_ACCENT, command=self.on_clean)
        btn.pack(side="right")
        self._busy_widgets.append(btn)
        self.freed_label = ctk.CTkLabel(bar, text="—", font=(FONT_FAMILY, 13, "bold"),
                                        text_color=COL_SUCCESS)
        self.freed_label.pack(side="left", padx=14)

    def on_clean(self):
        keys = [key for key, var in self._clean_vars if var.get()]
        if not keys:
            self.log(self.t("log_none_selected"), "warn")
            return
        self._run_task(self._task_clean, keys)

    def _task_clean(self, keys):
        self.log(self.t("log_clean_start"), "info")
        total = 0

        def report_total():
            self._post(lambda: self.freed_label.configure(
                text=self.t("label_freed", size=fmt_bytes(total))))

        groups = []
        if "user_temp" in keys:
            groups.append(("clean_user_temp", [tempfile.gettempdir()]))
        if "win_temp" in keys:
            groups.append(("clean_win_temp",
                           [os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Temp")]))
        if "shader" in keys:
            dirs = shader_cache_dirs()
            if dirs:
                groups.append(("clean_shader", dirs))
            else:
                self.log(self.t("log_shader_none"), "dim")

        for name_key, dirs in groups:
            self.log(self.t("log_clean_target", name=self.t(name_key)), "info")
            for directory in dirs:
                freed, removed, failed = clean_directory(directory)
                total += freed
                report_total()
                self.log(self.t("log_clean_result", path=directory, size=fmt_bytes(freed),
                                files=removed, failed=failed),
                         "success" if freed > 0 else "dim")

        if "dns" in keys:
            rc, out = run_simple(["ipconfig", "/flushdns"])
            if rc == 0:
                self.log(self.t("log_dns_ok"), "success")
            else:
                self.log((out or "ipconfig /flushdns failed").strip(), "error")

        self.log(self.t("log_clean_done", size=fmt_bytes(total)), "success")

    # ---------------------------------------------------- tab: startup -----

    def _build_startup_tab(self, tab):
        ctk.CTkLabel(tab, text=self.t("startup_desc"), font=(FONT_FAMILY, 11),
                     text_color=COL_TEXT_DIM, wraplength=900, justify="left",
                     anchor="w").pack(anchor="w", padx=16, pady=(10, 4))

        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=4)
        self.startup_status_label = ctk.CTkLabel(bar, text="…",
                                                 font=(FONT_FAMILY, 12, "bold"),
                                                 text_color=COL_TEXT_DIM)
        self.startup_status_label.pack(side="left")
        btn = ctk.CTkButton(bar, text=self.t("btn_refresh"), width=150, height=32,
                            corner_radius=8, fg_color=COL_ACCENT,
                            hover_color=COL_ACCENT_HOVER, text_color=COL_ON_ACCENT,
                            command=self.on_startup_refresh)
        btn.pack(side="right")
        self._busy_widgets.append(btn)

        self.startup_scroll = ctk.CTkScrollableFrame(tab, fg_color=COL_CARD_2)
        self.startup_scroll.pack(fill="both", expand=True, padx=16, pady=(4, 12))
        self._startup_switches = []
        self._populate_startup_rows([])
        self.after(300, self.on_startup_refresh)          # initial scan

    def _populate_startup_rows(self, items):
        for widget in self.startup_scroll.winfo_children():
            widget.destroy()
        self._startup_switches = []
        if not items:
            ctk.CTkLabel(self.startup_scroll, text=self.t("startup_empty"),
                         font=(FONT_FAMILY, 12), text_color=COL_TEXT_DIM).pack(pady=18)
        for item in items:
            row = ctk.CTkFrame(self.startup_scroll, fg_color=COL_CARD, corner_radius=8)
            row.pack(fill="x", padx=8, pady=4)
            texts = ctk.CTkFrame(row, fg_color="transparent")
            texts.pack(side="left", fill="x", expand=True, padx=(12, 6), pady=8)
            ctk.CTkLabel(texts, text=item["name"], font=(FONT_FAMILY, 12, "bold"),
                         text_color=COL_TEXT if not item["disabled"] else COL_TEXT_DIM,
                         anchor="w").pack(anchor="w")
            ctk.CTkLabel(texts, text=item["command"], font=(FONT_FAMILY, 10),
                         text_color=COL_TEXT_DIM, anchor="w", wraplength=620,
                         justify="left").pack(anchor="w")
            var = ctk.BooleanVar(value=not item["disabled"])
            switch = ctk.CTkSwitch(row, text="", variable=var, width=56,
                                   progress_color=COL_ACCENT,
                                   command=lambda it=item: self.on_startup_toggle(it))
            switch.pack(side="right", padx=(4, 12))
            source = item["source"] if item["source"] != "Folder" else self.t("src_folder")
            ctk.CTkLabel(row, text=source, font=(FONT_FAMILY, 10, "bold"),
                         text_color=COL_ACCENT if not item["disabled"] else COL_TEXT_DIM
                         ).pack(side="right", padx=(4, 8))
            self._startup_switches.append(switch)
        disabled_count = sum(1 for it in items if it["disabled"])
        self.startup_status_label.configure(
            text=self.t("startup_status", n=len(items), d=disabled_count))

    def on_startup_refresh(self):
        self._run_task(self._task_startup_refresh)

    def _task_startup_refresh(self):
        self.log(self.t("log_startup_scan"), "info")
        items = scan_startup_items()
        self.log(self.t("log_startup_scan_done", n=len(items)), "dim")
        self._post(lambda: self._populate_startup_rows(items))

    def on_startup_toggle(self, item):
        self._run_task(self._task_startup_toggle, item)

    def _task_startup_toggle(self, item):
        disable = not item["disabled"]
        try:
            if item["source"] == "Folder":
                startup_toggle_folder(item, disable)
            else:
                startup_toggle_registry(item, disable)
            key = "log_startup_disable" if disable else "log_startup_enable"
            self.log(self.t(key, name=item["name"], source=item["source"]), "success")
        except Exception as exc:
            self.log(self.t("log_startup_err", name=item["name"], err=exc), "error")
        items = scan_startup_items()
        self._post(lambda: self._populate_startup_rows(items))

    # -------------------------------------------------- restore point ------

    def on_restore_point(self):
        self._run_task(self._task_restore_point)

    def _task_restore_point(self):
        self.log(self.t("log_rp_start"), "info")
        _rc, out = run_powershell(ps_restore_point(), timeout=300)
        for line in (l.strip() for l in out.splitlines()):
            if not line:
                continue
            if line.startswith("RP_OK"):
                self.log(self.t("log_rp_ok"), "success")
            elif line.startswith("RP_ERR:"):
                self.log(self.t("log_rp_err", err=line.split(":", 1)[1]), "error")
            else:
                self.log(line, "raw")


def main():
    if os.name != "nt":
        sys.exit(f"{APP_NAME} only runs on Windows.")

    if not is_admin():
        if relaunch_elevated():
            sys.exit(0)                      # elevated copy now starting
        ctypes.windll.user32.MessageBoxW(
            0,
            "WinExhale requires administrator privileges.\n\n"
            "WinExhale nécessite des privilèges administrateur.",
            APP_NAME, 0x00000010)
        sys.exit(1)

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = WinExhaleApp()
    app.mainloop()


if __name__ == "__main__":
    main()
