#!/usr/bin/env python3
"""
🔐 Browser Kill Switch - Signs out of every installed browser (Chrome, Edge, Brave, Opera, Vivaldi,
Firefox, Safari and more) and clears password cache
"""

import configparser
import glob
import os
import shutil
import subprocess
import sys
import time
from collections import namedtuple
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue
import signal
import select


# Browser engines - each one lays out its profile data differently
CHROMIUM = "chromium"
FIREFOX = "firefox"
SAFARI = "safari"

# data_dirs: folders holding the profiles; cache_dirs: separate per-profile cache folders, if any.
# processes: image names for taskkill on Windows, pkill patterns (case-sensitive) on macOS/Linux.
Browser = namedtuple("Browser", ["name", "engine", "data_dirs", "cache_dirs", "processes"])


# Chromium-based browsers (Chrome, Edge, Brave, Opera, Vivaldi, Yandex, Arc): files to remove
CHROMIUM_FILES = [
    "Login Data",
    "Login Data-journal",
    "Login Data For Account",
    "Login Data For Account-journal",
    "Cookies",
    "Cookies-journal",
    "Web Data",
    "Web Data-journal",
    "Account Web Data",
    "Account Web Data-journal",
    "History",
    "History-journal",
    "Visited Links",
    "Archived History",
    "Archived History-journal",
    "Current Session",
    "Current Tabs",
    "Last Session",
    "Last Tabs",
    "Shortcuts",
    "Shortcuts-journal",
    "Top Sites",
    "Top Sites-journal",
    "Favicons",
    "Favicons-journal",
    "Bookmarks",
    "Bookmarks.bak",
    "Preferences",
    "Secure Preferences",
    "TransportSecurity",
    "Trust Tokens",
    "Network Action Predictor",
    "Network Persistent State",
    "Network Service State",
    "Origin Bound Certs",
    "QuotaManager",
    "QuotaManager-journal"
]

# Chromium-based browsers: directories to remove
CHROMIUM_DIRS = [
    "Cache",
    "Code Cache",
    "GPUCache",
    "CacheStorage",
    "Sessions",
    "Session Storage",
    "Local Storage",
    "IndexedDB",
    "Service Worker",
    "Network",
    "Storage",
    "Site Characteristics Database",
    "BrowserMetrics",
    "BrowsingTopics",
    "shared_proto_db",
    "OptimizationHints",
    "Sync App Settings",
    "Sync Data",
    "GrShaderCache",
    "ShaderCache",
    "AutofillStrikeDatabase"
]

# Firefox-based browsers (Firefox, Waterfox, LibreWolf, Floorp, Zen): files to remove
FIREFOX_FILES = [
    "logins.json",
    "logins-backup.json",
    "logins.db",
    "key4.db",
    "key3.db",
    "signons.sqlite",
    "signedInUser.json",
    "cookies.sqlite",
    "cookies.sqlite-wal",
    "cookies.sqlite-shm",
    "places.sqlite",
    "places.sqlite-wal",
    "places.sqlite-shm",
    "favicons.sqlite",
    "favicons.sqlite-wal",
    "favicons.sqlite-shm",
    "formhistory.sqlite",
    "formhistory.sqlite-wal",
    "formhistory.sqlite-shm",
    "autofill-profiles.json",
    "webappsstore.sqlite",
    "webappsstore.sqlite-wal",
    "webappsstore.sqlite-shm",
    "sessionstore.jsonlz4",
    "sessionCheckpoints.json",
    "permissions.sqlite",
    "content-prefs.sqlite",
    "credentialstate.sqlite",
    "storage.sqlite",
    "SiteSecurityServiceState.txt",
    "SiteSecurityServiceState.bin"
]

# Firefox-based browsers: directories to remove
FIREFOX_DIRS = [
    "storage",
    "sessionstore-backups",
    "bookmarkbackups",
    "weave",
    "cache2",
    "startupCache",
    "thumbnails",
    "jumpListCache",
    "shader-cache",
    "OfflineCache"
]

# Safari (macOS): files to remove. Saved passwords live in the Keychain and are not touched.
SAFARI_FILES = [
    "History.db",
    "History.db-wal",
    "History.db-shm",
    "History.db-lock",
    "LastSession.plist",
    "RecentlyClosedTabs.plist",
    "TopSites.plist",
    "Bookmarks.plist",
    "Downloads.plist",
    "Form Values",
    "CloudTabs.db",
    "CloudTabs.db-wal",
    "CloudTabs.db-shm",
    "Cookies.binarycookies",
    "HSTS.plist",
    "Cache.db",
    "Cache.db-wal",
    "Cache.db-shm"
]

# Safari: directories to remove
SAFARI_DIRS = [
    "LocalStorage",
    "Databases",
    "WebsiteData",
    "Favicon Cache",
    "Touch Icons Cache",
    "Template Icons",
    "WebKitCache",
    "fsCachedData"
]

SENSITIVE_ITEMS = {
    CHROMIUM: (CHROMIUM_FILES, CHROMIUM_DIRS),
    FIREFOX: (FIREFOX_FILES, FIREFOX_DIRS),
    SAFARI: (SAFARI_FILES, SAFARI_DIRS),
}

# Firefox keeps the last signed-in account's email in prefs.js even after signedInUser.json is gone
FIREFOX_ACCOUNT_PREFS = ('user_pref("services.sync.', 'user_pref("identity.fxaccounts.')


def get_browsers():
    """Return every browser this tool knows about, with its data folders and process names for this OS."""
    home = os.path.expanduser("~")
    join = os.path.join

    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA") or join(home, "AppData", "Local")
        roaming = os.environ.get("APPDATA") or join(home, "AppData", "Roaming")
        # The Microsoft Store build of Firefox keeps its data inside its app package
        firefox_store = glob.glob(join(local, "Packages", "Mozilla.Firefox_*", "LocalCache"))
        chrome = ["chrome.exe", "chrome_crashpad_handler.exe", "chrome_elf.exe", "chromedriver.exe"]
        # msedgewebview2.exe is left alone - Outlook, Teams and other apps run on it
        edge = ["msedge.exe", "msedgedriver.exe"]
        return [
            Browser("Google Chrome", CHROMIUM, [join(local, "Google", "Chrome", "User Data")], [], chrome),
            Browser("Google Chrome Beta", CHROMIUM, [join(local, "Google", "Chrome Beta", "User Data")], [], chrome),
            Browser("Google Chrome Dev", CHROMIUM, [join(local, "Google", "Chrome Dev", "User Data")], [], chrome),
            Browser("Google Chrome Canary", CHROMIUM, [join(local, "Google", "Chrome SxS", "User Data")], [], chrome),
            Browser("Chromium", CHROMIUM, [join(local, "Chromium", "User Data")], [], chrome),
            Browser("Microsoft Edge", CHROMIUM, [join(local, "Microsoft", "Edge", "User Data")], [], edge),
            Browser("Microsoft Edge Beta", CHROMIUM, [join(local, "Microsoft", "Edge Beta", "User Data")], [], edge),
            Browser("Microsoft Edge Dev", CHROMIUM, [join(local, "Microsoft", "Edge Dev", "User Data")], [], edge),
            Browser("Microsoft Edge Canary", CHROMIUM, [join(local, "Microsoft", "Edge SxS", "User Data")], [], edge),
            Browser("Brave", CHROMIUM, [join(local, "BraveSoftware", "Brave-Browser", "User Data")], [],
                    ["brave.exe"]),
            Browser("Vivaldi", CHROMIUM, [join(local, "Vivaldi", "User Data")], [], ["vivaldi.exe"]),
            Browser("Opera", CHROMIUM, [join(roaming, "Opera Software", "Opera Stable")],
                    [join(local, "Opera Software", "Opera Stable")], ["opera.exe"]),
            Browser("Opera GX", CHROMIUM, [join(roaming, "Opera Software", "Opera GX Stable")],
                    [join(local, "Opera Software", "Opera GX Stable")], ["opera.exe"]),
            # Yandex runs as the generic browser.exe - it is only killed when Yandex's data folder exists
            Browser("Yandex", CHROMIUM, [join(local, "Yandex", "YandexBrowser", "User Data")], [], ["browser.exe"]),
            Browser("Arc", CHROMIUM,
                    glob.glob(join(local, "Packages", "TheBrowserCompany.Arc_*", "LocalCache", "Local", "Arc",
                                   "User Data")), [], ["Arc.exe"]),
            Browser("Firefox", FIREFOX,
                    [join(roaming, "Mozilla", "Firefox")]
                    + [join(p, "Roaming", "Mozilla", "Firefox") for p in firefox_store],
                    [join(local, "Mozilla", "Firefox")]
                    + [join(p, "Local", "Mozilla", "Firefox") for p in firefox_store],
                    ["firefox.exe"]),
            Browser("Waterfox", FIREFOX, [join(roaming, "Waterfox")], [join(local, "Waterfox")], ["waterfox.exe"]),
            Browser("LibreWolf", FIREFOX, [join(roaming, "librewolf")], [join(local, "librewolf")],
                    ["librewolf.exe"]),
            Browser("Floorp", FIREFOX, [join(roaming, "Floorp")], [join(local, "Floorp")], ["floorp.exe"]),
            Browser("Zen", FIREFOX, [join(roaming, "zen")], [join(local, "zen")], ["zen.exe"]),
        ]

    if sys.platform == "darwin":  # macOS
        support = join(home, "Library", "Application Support")
        caches = join(home, "Library", "Caches")
        safari_container = join(home, "Library", "Containers", "com.apple.Safari", "Data", "Library")

        def chromium(name, folder, process):
            return Browser(name, CHROMIUM, [join(support, folder)], [join(caches, folder)], [process])

        def firefox(name, folder, process):
            return Browser(name, FIREFOX, [join(support, folder)], [join(caches, folder)], [process])

        return [
            chromium("Google Chrome", join("Google", "Chrome"), "Google Chrome"),
            chromium("Google Chrome Beta", join("Google", "Chrome Beta"), "Google Chrome"),
            chromium("Google Chrome Dev", join("Google", "Chrome Dev"), "Google Chrome"),
            chromium("Google Chrome Canary", join("Google", "Chrome Canary"), "Google Chrome"),
            chromium("Chromium", "Chromium", "Chromium"),
            chromium("Microsoft Edge", "Microsoft Edge", "Microsoft Edge"),
            chromium("Microsoft Edge Beta", "Microsoft Edge Beta", "Microsoft Edge"),
            chromium("Microsoft Edge Dev", "Microsoft Edge Dev", "Microsoft Edge"),
            chromium("Microsoft Edge Canary", "Microsoft Edge Canary", "Microsoft Edge"),
            chromium("Brave", join("BraveSoftware", "Brave-Browser"), "Brave Browser"),
            chromium("Vivaldi", "Vivaldi", "Vivaldi"),
            chromium("Opera", "com.operasoftware.Opera", "Opera"),
            chromium("Opera GX", "com.operasoftware.OperaGX", "Opera"),
            chromium("Yandex", join("Yandex", "YandexBrowser"), "Yandex"),
            chromium("Arc", join("Arc", "User Data"), "^Arc$"),
            firefox("Firefox", "Firefox", "firefox"),
            firefox("Waterfox", "Waterfox", "waterfox"),
            firefox("LibreWolf", "librewolf", "librewolf"),
            firefox("Floorp", "Floorp", "floorp"),
            firefox("Zen", "zen", "^zen$"),
            # Safari has no profiles - each folder below is cleaned as-is
            Browser("Safari", SAFARI,
                    [join(home, "Library", "Safari"), join(home, "Library", "Cookies"),
                     join(safari_container, "Cookies"), join(home, "Library", "WebKit", "com.apple.Safari")],
                    [join(caches, "com.apple.Safari"), join(safari_container, "Caches", "com.apple.Safari")],
                    ["^Safari$"]),
        ]

    # Linux (including snap and flatpak installs)
    config = os.environ.get("XDG_CONFIG_HOME") or join(home, ".config")
    cache = os.environ.get("XDG_CACHE_HOME") or join(home, ".cache")
    snap = join(home, "snap")
    flatpak = join(home, ".var", "app")

    def chromium(name, folder, process, extra_dirs=()):
        return Browser(name, CHROMIUM, [join(config, folder)] + list(extra_dirs), [join(cache, folder)], [process])

    return [
        chromium("Google Chrome", "google-chrome", "chrome",
                 [join(flatpak, "com.google.Chrome", "config", "google-chrome")]),
        chromium("Google Chrome Beta", "google-chrome-beta", "chrome"),
        chromium("Google Chrome Dev", "google-chrome-unstable", "chrome"),
        chromium("Chromium", "chromium", "chrom(e|ium)",
                 [join(snap, "chromium", "common", "chromium"),
                  join(flatpak, "org.chromium.Chromium", "config", "chromium")]),
        chromium("Microsoft Edge", "microsoft-edge", "msedge",
                 [join(flatpak, "com.microsoft.Edge", "config", "microsoft-edge")]),
        chromium("Microsoft Edge Beta", "microsoft-edge-beta", "msedge"),
        chromium("Microsoft Edge Dev", "microsoft-edge-dev", "msedge"),
        chromium("Brave", join("BraveSoftware", "Brave-Browser"), "brave",
                 [join(flatpak, "com.brave.Browser", "config", "BraveSoftware", "Brave-Browser")]),
        chromium("Vivaldi", "vivaldi", "vivaldi"),
        chromium("Opera", "opera", "opera"),
        chromium("Yandex", "yandex-browser", "yandex"),
        Browser("Firefox", FIREFOX,
                [join(home, ".mozilla", "firefox"), join(snap, "firefox", "common", ".mozilla", "firefox"),
                 join(flatpak, "org.mozilla.firefox", ".mozilla", "firefox")],
                [join(cache, "mozilla", "firefox"), join(snap, "firefox", "common", ".cache", "mozilla", "firefox")],
                ["firefox"]),
        Browser("Waterfox", FIREFOX, [join(home, ".waterfox")], [join(cache, "waterfox")], ["waterfox"]),
        Browser("LibreWolf", FIREFOX, [join(home, ".librewolf")], [join(cache, "librewolf")], ["librewolf"]),
        Browser("Floorp", FIREFOX, [join(home, ".floorp")], [join(cache, "floorp")], ["floorp"]),
        Browser("Zen", FIREFOX, [join(home, ".zen")], [join(cache, "zen")], ["^zen(-bin)?$"]),
    ]


def find_profiles(root, engine):
    """Return the profile folders inside a browser data (or cache) folder."""
    if engine == SAFARI:
        return [root]

    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return []

    profiles = []
    if engine == CHROMIUM:
        # Opera keeps its profile in the root folder itself rather than in "Default"
        if any(os.path.exists(os.path.join(root, marker)) for marker in ("Preferences", "Login Data", "Cache")):
            profiles.append(root)
        profiles += [os.path.join(root, d) for d in entries if d == "Default" or d.startswith("Profile ")]
    else:
        # Firefox lists its profiles in profiles.ini; they live in "Profiles" on Windows/macOS
        # and directly in the root folder on Linux
        ini_path = os.path.join(root, "profiles.ini")
        if os.path.isfile(ini_path):
            parser = configparser.RawConfigParser()
            try:
                parser.read(ini_path, encoding="utf-8")
            except (configparser.Error, UnicodeDecodeError):
                pass
            for section in parser.sections():
                path = parser.get(section, "Path", fallback=None)
                if path:
                    if parser.get(section, "IsRelative", fallback="1") == "1":
                        path = os.path.join(root, path)
                    profiles.append(os.path.normpath(path))

        profiles_dir = os.path.join(root, "Profiles")
        if os.path.isdir(profiles_dir):
            profiles += [os.path.join(profiles_dir, d) for d in sorted(os.listdir(profiles_dir))]
        profiles += [os.path.join(root, d) for d in entries
                     if any(os.path.exists(os.path.join(root, d, marker)) for marker in ("prefs.js", "cache2"))]

    unique = {}
    for path in profiles:
        if os.path.isdir(path):
            unique.setdefault(os.path.normcase(os.path.abspath(path)), path)
    return list(unique.values())


def remove_firefox_account_prefs(profile_path):
    """Drop the Firefox account and sync settings from prefs.js, keeping every other setting.
    Returns True if any were removed."""
    prefs_path = os.path.join(profile_path, "prefs.js")
    try:
        with open(prefs_path, encoding="utf-8", newline="") as f:
            lines = f.readlines()
        kept = [line for line in lines if not line.startswith(FIREFOX_ACCOUNT_PREFS)]
        if len(kept) == len(lines):
            return False
        with open(prefs_path, "w", encoding="utf-8", newline="") as f:
            f.writelines(kept)
        return True
    except (OSError, UnicodeDecodeError):
        return False


def windows_work_accounts():
    """Return the work or school organizations Windows itself is signed in to (empty off Windows)."""
    if sys.platform != "win32":
        return []
    try:
        output = subprocess.run(["dsregcmd", "/status"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return []

    status = {}
    for line in output.splitlines():
        key, separator, value = line.partition(" : ")
        if separator:
            status[key.strip()] = value.strip()

    organizations = []
    if status.get("AzureAdJoined") == "YES":
        organizations.append(status.get("TenantName") or "your organization")
    if status.get("WorkplaceJoined") == "YES":
        organizations.append(status.get("WorkplaceTenantName") or "your organization")
    return organizations


def wait_for_input_with_timeout(timeout_seconds=3):
    """Wait for user input with a timeout. Returns True if input received, False if timeout."""
    if sys.platform == "win32":
        # Windows implementation using threading
        result = [False]

        def input_thread():
            try:
                input()
                result[0] = True
            except:
                pass

        thread = threading.Thread(target=input_thread, daemon=True)
        thread.start()
        thread.join(timeout_seconds)

        return result[0]
    else:
        # Unix/Linux implementation
        try:
            ready, _, _ = select.select([sys.stdin], [], [], timeout_seconds)
            if ready:
                input()
                return True
            return False
        except:
            return False


def shutdown_computer():
    """Shutdown the computer based on the operating system."""
    print("\n🔌 No response received. Shutting down computer in 5 seconds...")
    print("⚠️ Press Ctrl+C to cancel shutdown!")

    try:
        time.sleep(5)
        if sys.platform == "win32":
            subprocess.run(["shutdown", "/s", "/t", "0"], check=True)
        elif sys.platform == "darwin":  # macOS
            subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
        else:  # Linux
            subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
    except KeyboardInterrupt:
        print("\n✅ Shutdown cancelled by user.")
        return False
    except Exception as e:
        print(f"\n❌ Failed to shutdown computer: {str(e)}")
        return False

    return True


def kill_browser_processes(browsers):
    """Kill the running processes of the given browsers with retries."""
    print("🛑 Closing any running browser instances...")

    # Several browsers share a process name (Chrome channels, Opera and Opera GX) - kill each once
    process_names = []
    for browser in browsers:
        for process in browser.processes:
            if process not in process_names:
                process_names.append(process)

    success = False
    max_attempts = 3

    for attempt in range(max_attempts):
        try:
            if sys.platform == "win32":
                # Kill all browser processes - force kill immediately for speed
                for process in process_names:
                    subprocess.run(["taskkill", "/F", "/IM", process],
                                 stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=False)
            else:
                for process in process_names:
                    subprocess.run(["pkill", process],
                                 stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=False)
                time.sleep(2)
                for process in process_names:
                    subprocess.run(["pkill", "-9", process],
                                 stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=False)

            time.sleep(0.5)  # Minimal delay for processes to exit
            success = True
            break
        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} to close browsers failed: {str(e)}")
            time.sleep(0.5)  # Reduced retry delay

    if not success:
        print("⚠️ Warning: Browser processes may still be running")
    return success

def retry_remove_file(file_path, max_attempts=3):
    """Safely attempt to remove a file with retries."""
    for attempt in range(max_attempts):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            return True
        except Exception:
            if attempt < max_attempts - 1:
                time.sleep(0.1)  # Much faster retry for file operations
                continue
            return False
    return False

def retry_remove_directory(dir_path, max_attempts=3):
    """Safely attempt to remove a directory with retries."""
    for attempt in range(max_attempts):
        try:
            if os.path.exists(dir_path):
                shutil.rmtree(dir_path)
            return True
        except Exception:
            if attempt < max_attempts - 1:
                time.sleep(0.2)  # Faster retry for directory operations
                continue
            return False
    return False

def remove_file_threaded(file_path, file_name, results_queue):
    """Thread-safe file removal function."""
    try:
        if os.path.exists(file_path):
            if retry_remove_file(file_path):
                results_queue.put(("file_success", f"🗑️ Removed: {file_name}"))
                return True
            else:
                # Try to clear contents instead
                try:
                    with open(file_path, 'w') as f:
                        f.truncate(0)
                    results_queue.put(("file_success", f"✔️ Cleared contents of: {file_name}"))
                    return True
                except:
                    results_queue.put(("file_failed", f"⚠️ Could not remove {file_name}"))
                    return False
        return True
    except Exception as e:
        results_queue.put(("file_failed", f"⚠️ Error removing {file_name}: {str(e)}"))
        return False

def remove_directory_threaded(dir_path, dir_name, results_queue):
    """Thread-safe directory removal function."""
    try:
        if os.path.exists(dir_path):
            if retry_remove_directory(dir_path):
                results_queue.put(("dir_success", f"🗑️ Removed directory: {dir_name}"))
                return True
            else:
                # Try to clear contents instead
                try:
                    for root, dirs, files in os.walk(dir_path):
                        for f in files:
                            try:
                                os.remove(os.path.join(root, f))
                            except:
                                continue
                    results_queue.put(("dir_success", f"✔️ Cleared contents of directory: {dir_name}"))
                    return True
                except:
                    results_queue.put(("dir_failed", f"⚠️ Could not remove directory {dir_name}"))
                    return False
        return True
    except Exception as e:
        results_queue.put(("dir_failed", f"⚠️ Error removing directory {dir_name}: {str(e)}"))
        return False

def process_profile_threaded(profile_path, profile_name, sensitive_files, sensitive_dirs, results_queue):
    """Process a single browser profile using threading for files and directories."""
    results_queue.put(("info", f"\n🔄 Processing profile: {profile_name}"))

    success_count = 0
    total_operations = len(sensitive_files) + len(sensitive_dirs)

    # Use ThreadPoolExecutor for concurrent file and directory operations
    with ThreadPoolExecutor(max_workers=16) as executor:  # Significantly increased worker count for speed
        futures = []

        # Submit file removal tasks
        for file in sensitive_files:
            file_path = os.path.join(profile_path, file)
            future = executor.submit(remove_file_threaded, file_path, file, results_queue)
            futures.append(future)

        # Submit directory removal tasks
        for directory in sensitive_dirs:
            dir_path = os.path.join(profile_path, directory)
            future = executor.submit(remove_directory_threaded, dir_path, directory, results_queue)
            futures.append(future)

        # Wait for all operations to complete
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is True:
                    success_count += 1
            except Exception as e:
                results_queue.put(("error", f"⚠️ Thread error: {str(e)}"))

    return success_count, total_operations

def clear_browser_data(browser):
    """Clear one browser's login data, cookies, cached passwords, browsing history, and session data using threading."""
    sensitive_files, sensitive_dirs = SENSITIVE_ITEMS[browser.engine]

    data_dirs = [d for d in browser.data_dirs if os.path.isdir(d)]
    for data_dir in data_dirs:
        print(f"🔍 Found {browser.name} data directory at: {data_dir}")

    # Find all profiles, plus the separate cache folders some browsers keep for them
    profiles = []
    for data_dir in data_dirs:
        profiles += [(path, os.path.basename(path)) for path in find_profiles(data_dir, browser.engine)]
    caches = []
    for cache_dir in browser.cache_dirs:
        if os.path.isdir(cache_dir):
            caches += [(path, f"{os.path.basename(path)} (cache)") for path in find_profiles(cache_dir, browser.engine)]

    print(f"👤 Found {len(profiles)} {browser.name} profiles")

    if not profiles:
        print(f"❌ No {browser.name} profiles found to process")
        return False

    total_success_count = 0
    total_operations = 0

    # Use a queue for thread-safe communication
    results_queue = queue.Queue()

    # Process profiles in parallel using ThreadPoolExecutor
    targets = profiles + caches
    with ThreadPoolExecutor(max_workers=min(len(targets), 8)) as executor:  # Increased concurrent profiles
        futures = []

        for profile_path, profile_name in targets:
            future = executor.submit(
                process_profile_threaded,
                profile_path,
                profile_name,
                sensitive_files,
                sensitive_dirs,
                results_queue
            )
            futures.append(future)

        # Collect results from all profile processing threads
        for future in as_completed(futures):
            try:
                success_count, ops_count = future.result()
                total_operations += ops_count
                total_success_count += success_count
            except Exception:
                pass  # Ignore errors, just continue

    # Process messages from the queue
    messages = []
    while not results_queue.empty():
        try:
            msg_type, message = results_queue.get_nowait()
            messages.append((msg_type, message))
        except queue.Empty:
            break

    # Sort and display messages
    info_messages = [(msg_type, msg) for msg_type, msg in messages if msg_type == "info"]
    success_messages = [(msg_type, msg) for msg_type, msg in messages if msg_type.endswith("_success")]
    failed_messages = [(msg_type, msg) for msg_type, msg in messages if msg_type.endswith("_failed")]
    error_messages = [(msg_type, msg) for msg_type, msg in messages if msg_type == "error"]

    # Display messages in order
    for _, message in info_messages:
        print(message)
    for _, message in success_messages:
        print(message)
    for _, message in failed_messages:
        print(message)
    for _, message in error_messages:
        print(message)

    # Chromium browsers also keep session data and account state at the root of the data directory
    if browser.engine == CHROMIUM:
        for data_dir in data_dirs:
            # Process root-level directories in parallel
            root_dirs = ["Session Storage", "Local Storage", "Sync Data"]
            root_results_queue = queue.Queue()

            with ThreadPoolExecutor(max_workers=len(root_dirs)) as executor:
                root_futures = []
                for directory in root_dirs:
                    dir_path = os.path.join(data_dir, directory)
                    future = executor.submit(remove_directory_threaded, dir_path, f"root/{directory}", root_results_queue)
                    root_futures.append(future)

                # Wait for root directory operations
                for future in as_completed(root_futures):
                    try:
                        future.result()  # Just get the result, don't unpack
                        total_operations += 1
                    except:
                        total_operations += 1

            # Process root directory messages
            while not root_results_queue.empty():
                try:
                    msg_type, message = root_results_queue.get_nowait()
                    print(message)
                    if msg_type.endswith("_success"):
                        total_success_count += 1
                except queue.Empty:
                    break

            # Final cleanup: try to remove or clear the Local State file
            local_state_path = os.path.join(data_dir, "Local State")
            if os.path.exists(local_state_path):
                try:
                    os.remove(local_state_path)
                    print("🗑️ Removed Local State file")
                except:
                    try:
                        with open(local_state_path, 'w') as f:
                            f.write("{}")
                        print("✔️ Cleared Local State file")
                    except:
                        print("⚠️ Could not modify Local State file")

    if browser.engine == FIREFOX:
        for profile_path, profile_name in profiles:
            if remove_firefox_account_prefs(profile_path):
                print(f"🗑️ Removed saved account settings from prefs.js: {profile_name}")

    success_rate = (total_success_count / total_operations * 100) if total_operations > 0 else 0
    print(f"\n📊 {browser.name} clean-up completed: {success_rate:.1f}% successful ({total_success_count}/{total_operations} operations)")

    return True

def clear_all_browsers():
    """Find every installed browser, close it, and clear its data."""
    browsers = [b for b in get_browsers() if any(os.path.isdir(d) for d in b.data_dirs)]

    if not browsers:
        print("❌ No supported browser data found on this computer")
        return False

    print(f"🌐 Found {len(browsers)} browsers: {', '.join(b.name for b in browsers)}")

    # Ensure every browser is fully closed so its files are not locked
    kill_browser_processes(browsers)
    time.sleep(0.1)  # Reduced delay after killing processes

    cleaned_count = 0
    for browser in browsers:
        print("\n" + "-" * 60)
        print(f"🧹 {browser.name}")
        print("-" * 60)
        try:
            if clear_browser_data(browser):
                cleaned_count += 1
        except Exception as e:
            # Keep going - one browser failing must not leave the others signed in
            print(f"❌ Error while clearing {browser.name}: {str(e)}")

    return cleaned_count > 0

def main():
    print("\n" + "=" * 60)
    print("🔐 BROWSER KILL SWITCH - Sign Out & Clear Data 🔐")
    print("🚀 ENHANCED WITH THREADING FOR FASTER PERFORMANCE 🚀")
    print("=" * 60 + "\n")

    start_time = time.time()

    try:
        # Clear sensitive data
        if clear_all_browsers():
            end_time = time.time()
            elapsed_time = end_time - start_time
            print(f"\n✅ Browser data cleanup completed in {elapsed_time:.2f} seconds.")
            print("🔒 You should now be signed out of all browser profiles.")
        else:
            end_time = time.time()
            elapsed_time = end_time - start_time
            print(f"\n❌ Some browser data could not be cleared. Check the log above.")
            print(f"⏱️ Operation completed in {elapsed_time:.2f} seconds.")

        # Edge (and Microsoft sign-in pages) offer the account Windows is signed in to - no browser file holds it
        for organization in windows_work_accounts():
            print(f"\n⚠️ Windows itself is signed in to a work or school account ({organization}).")
            print("   Edge and Microsoft sign-in pages get that account from Windows, so they will keep offering it")
            print("   (or sign straight back in) - deleting browser data cannot remove it.")
            print("   To remove it: Settings > Accounts > Access work or school > Disconnect.")
            print("   That also signs out Outlook, Teams and OneDrive, and on a company PC may need your IT admin.")

        print("\n👋 Press Enter to exit (3 second timeout)...", end="")
        sys.stdout.flush()

        # Wait for input with timeout
        if not wait_for_input_with_timeout(3):
            shutdown_computer()

    except KeyboardInterrupt:
        print("\n\n⚠️ Operation cancelled by user.")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {str(e)}")
        print("\n👋 Press Enter to exit (3 second timeout)...", end="")
        sys.stdout.flush()

        if not wait_for_input_with_timeout(3):
            shutdown_computer()


if __name__ == "__main__":
    main()
