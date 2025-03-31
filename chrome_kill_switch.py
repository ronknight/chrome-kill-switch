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
    """Kill any running Chrome processes."""
    print("🛑 Closing any running Chrome instances...")
    
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], 
                          stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=False)
        else:
            subprocess.run(["pkill", "-f", "chrome"], 
                          stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=False)
        time.sleep(2)  # Give Chrome time to close
    except Exception as e:
        print(f"❌ Error closing Chrome: {e}")


def clear_chrome_data():
    """Clear Chrome login data, cookies, and cached passwords."""
    chrome_data_path = get_chrome_data_path()
    
    if not os.path.exists(chrome_data_path):
        print(f"❌ Chrome data directory not found at: {chrome_data_path}")
        return False
    
    print(f"🔍 Found Chrome data directory at: {chrome_data_path}")
    
    # Files and directories to remove for security cleanup
    sensitive_files = [
        "Login Data",
        "Login Data-journal",
        "Cookies",
        "Cookies-journal",
        "Web Data",
        "Web Data-journal"
    ]
    
    # Process each profile directory
    profile_count = 0
    
    try:
        # Check Default profile and any numbered profiles
        profiles = [d for d in os.listdir(chrome_data_path) 
                  if os.path.isdir(os.path.join(chrome_data_path, d)) and 
                  (d == "Default" or d.startswith("Profile "))]
        
        print(f"👤 Found {len(profiles)} Chrome profiles")
        
        for profile in profiles:
            profile_path = os.path.join(chrome_data_path, profile)
            profile_count += 1
            
            print(f"🔄 Processing profile: {profile}")
            
            # Remove sensitive files from this profile
            for file in sensitive_files:
                file_path = os.path.join(profile_path, file)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        print(f"🗑️ Removed: {file}")
                    except Exception as e:
                        print(f"⚠️ Failed to remove {file}: {e}")
            
            # Remove the Cache directory
            cache_path = os.path.join(profile_path, "Cache")
            if os.path.exists(cache_path):
                try:
                    shutil.rmtree(cache_path)
                    print(f"🗑️ Removed Cache directory in {profile}")
                except Exception as e:
                    print(f"⚠️ Failed to remove Cache directory: {e}")
        
        return profile_count > 0
    
    except Exception as e:
        print(f"❌ Error clearing Chrome data: {e}")
        return False


def main():
    print("\n" + "=" * 60)
    print("🔐 CHROME KILL SWITCH - Sign Out & Clear Passwords 🔐")
    print("=" * 60)
    
    # First, ensure Chrome is not running
    kill_chrome_processes()
    
    # Clear sensitive data
    if clear_chrome_data():
        print("\n✅ Successfully cleared Chrome login data and passwords.")
        print("🔒 You are now signed out of all Chrome profiles on this PC.")
    else:
        print("\n❌ Failed to clear some Chrome data. Check the log above for details.")
    
    print("\n👋 Press Enter to exit...", end="")
    input()


if __name__ == "__main__":
    main()