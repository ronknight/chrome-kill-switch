#!/usr/bin/env python3
"""
🔐 Chrome Kill Switch - Signs out of Chrome profiles and clears password cache
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def get_chrome_data_path():
    """Return the path to Chrome user data directory based on the current OS."""
    if sys.platform == "win32":
        return os.path.join(os.environ["USERPROFILE"], 
                           "AppData", "Local", "Google", "Chrome", "User Data")
    elif sys.platform == "darwin":  # macOS
        return os.path.join(os.environ["HOME"], 
                           "Library", "Application Support", "Google", "Chrome")
    else:  # Linux
        return os.path.join(os.environ["HOME"], ".config", "google-chrome")


def kill_chrome_processes():
    """Kill any running Chrome processes with retries."""
    print("🛑 Closing any running Chrome instances...")
    
    chrome_processes = [
        "chrome.exe",
        "chrome_crashpad_handler.exe",
        "chrome_elf.exe",
        "chromedriver.exe"
    ]
    
    success = False
    max_attempts = 3
    
    for attempt in range(max_attempts):
        try:
            if sys.platform == "win32":
                # Kill all Chrome-related processes
                for process in chrome_processes:
                    # First try graceful shutdown
                    subprocess.run(["taskkill", "/IM", process], 
                                 stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=False)
                time.sleep(2)
                
                # Then force kill all Chrome-related processes
                for process in chrome_processes:
                    subprocess.run(["taskkill", "/F", "/IM", process], 
                                 stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=False)
            else:
                subprocess.run(["pkill", "chrome"], 
                             stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=False)
                time.sleep(2)
                subprocess.run(["pkill", "-9", "chrome"], 
                             stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=False)
            
            time.sleep(3)  # Give more time for processes to fully exit
            success = True
            break
        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} to close Chrome failed: {str(e)}")
            time.sleep(2)
    
    if not success:
        print("⚠️ Warning: Chrome processes may still be running")
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
                time.sleep(1)  # Short delay between attempts
                continue
            return False
    return False

def retry_remove_directory(dir_path, max_attempts=3):
    """Safely attempt to remove a directory with retries."""
    for attempt in range(max_attempts):
        try:
            if os.path.exists(dir_path):
                if sys.platform == "win32":
                    subprocess.run(["rd", "/s", "/q", dir_path], 
                                 stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=False)
                else:
                    shutil.rmtree(dir_path)
            return True
        except Exception:
            if attempt < max_attempts - 1:
                time.sleep(2)  # Longer delay for directories
                continue
            return False
    return False

def clear_chrome_data():
    """Clear Chrome login data, cookies, cached passwords, browsing history, and session data."""
    chrome_data_path = get_chrome_data_path()
    
    if not os.path.exists(chrome_data_path):
        print(f"❌ Chrome data directory not found at: {chrome_data_path}")
        return False
    
    print(f"🔍 Found Chrome data directory at: {chrome_data_path}")
    
    # Files to remove for security cleanup
    sensitive_files = [
        "Login Data",
        "Login Data-journal",
        "Cookies",
        "Cookies-journal",
        "Web Data",
        "Web Data-journal",
        "History",
        "History-journal",
        "Visited Links",
        "Archived History",
        "Archived History-journal",
        "Current Session",
        "Current Tabs",
        "Last Session",
        "Last Tabs",
        "Sessions",
        "Shortcuts",
        "Shortcuts-journal",
        "Top Sites",
        "Top Sites-journal",
        "Favicons",
        "Favicons-journal",
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
    
    # Directories to remove
    sensitive_dirs = [
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
    
    # Process each profile directory
    profile_count = 0
    success_count = 0
    total_operations = 0
    
    try:
        # Ensure Chrome is fully closed
        kill_chrome_processes()
        time.sleep(2)  # Additional delay after killing processes
        
        # Try to remove the root-level "Sync Data" directory first
        sync_data_path = os.path.join(chrome_data_path, "Sync Data")
        if os.path.exists(sync_data_path):
            if retry_remove_directory(sync_data_path):
                print("🗑️ Removed Sync Data directory")
            
        # Find all Chrome profiles
        profiles = [d for d in os.listdir(chrome_data_path) 
                   if os.path.isdir(os.path.join(chrome_data_path, d)) and 
                   (d == "Default" or d.startswith("Profile "))]
        
        print(f"👤 Found {len(profiles)} Chrome profiles")
        
        for profile in profiles:
            profile_path = os.path.join(chrome_data_path, profile)
            profile_count += 1
            
            print(f"\n🔄 Processing profile: {profile}")
            
            # Remove sensitive files
            for file in sensitive_files:
                file_path = os.path.join(profile_path, file)
                total_operations += 1
                if os.path.exists(file_path):
                    if retry_remove_file(file_path):
                        print(f"🗑️ Removed: {file}")
                        success_count += 1
                    else:
                        print(f"⚠️ Could not remove {file}")
                        # If file removal failed, try to clear its contents
                        try:
                            with open(file_path, 'w') as f:
                                f.truncate(0)
                            print(f"✔️ Cleared contents of: {file}")
                            success_count += 1
                        except:
                            pass
            
            # Remove directories
            for directory in sensitive_dirs:
                dir_path = os.path.join(profile_path, directory)
                total_operations += 1
                if os.path.exists(dir_path):
                    if retry_remove_directory(dir_path):
                        print(f"🗑️ Removed directory: {directory}")
                        success_count += 1
                    else:
                        # If directory removal failed, try to clear its contents
                        try:
                            for root, dirs, files in os.walk(dir_path):
                                for f in files:
                                    try:
                                        os.remove(os.path.join(root, f))
                                    except:
                                        continue
                            print(f"✔️ Cleared contents of directory: {directory}")
                            success_count += 1
                        except:
                            print(f"⚠️ Could not remove directory {directory}")
        
        # Process root-level directories
        root_dirs = ["Session Storage", "Local Storage", "Sync Data"]
        for directory in root_dirs:
            dir_path = os.path.join(chrome_data_path, directory)
            total_operations += 1
            if os.path.exists(dir_path):
                if retry_remove_directory(dir_path):
                    print(f"🗑️ Removed root directory: {directory}")
                    success_count += 1
                else:
                    print(f"⚠️ Could not remove root directory {directory}")
        
        success_rate = (success_count / total_operations * 100) if total_operations > 0 else 0
        print(f"\n📊 Clean-up completed: {success_rate:.1f}% successful ({success_count}/{total_operations} operations)")
        
        # Final cleanup: try to remove or clear the Local State file
        local_state_path = os.path.join(chrome_data_path, "Local State")
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
        
        return profile_count > 0 and success_count > 0
        
    except Exception as e:
        print(f"❌ Error during cleanup: {str(e)}")
        return False

def main():
    print("\n" + "=" * 60)
    print("🔐 CHROME KILL SWITCH - Sign Out & Clear Data 🔐")
    print("=" * 60 + "\n")
    
    try:
        # Clear sensitive data
        if clear_chrome_data():
            print("\n✅ Chrome data cleanup completed.")
            print("🔒 You should now be signed out of all Chrome profiles.")
        else:
            print("\n❌ Some Chrome data could not be cleared. Check the log above.")
        
        print("\n👋 Press Enter to exit...", end="")
        input()
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Operation cancelled by user.")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {str(e)}")
        print("\nPress Enter to exit...", end="")
        input()


if __name__ == "__main__":
    main()