from cx_Freeze import setup, Executable

executables = [
    Executable(
        "chrome_kill_switch.py",
        target_name="ChromeKillSwitch.exe",
        icon=None,
        base="Console"
    )
]

setup(
    name="chrome_kill_switch",
    version="1.0",
    description="A tool to sign out Chrome profiles and clear password cache",
    author="User",
    options={
        "build_exe": {
            "packages": [],
            "excludes": [],
            "include_files": []
        },
    },
    executables=executables
)