"""Optional sign-in launch for the current Windows or Linux account."""

from pathlib import Path
import subprocess
import sys

NAME = "MarketIntelligenceAI"
REGISTRY_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"


def command_line(entrypoint):
    return [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(entrypoint)]


def linux_startup_path(config_directory: Path):
    return config_directory / "autostart" / "market-intelligence-ai.desktop"


def desktop_exec(args):
    def quote(value):
        value = value.replace("%", "%%")
        value = "".join("\\" + char if char in '\\"$`' else char for char in value)
        return '"' + value.replace("\\", "\\\\") + '"'

    if any("\n" in arg or "\r" in arg for arg in args):
        raise ValueError("Nombre de ruta incompatible con el inicio de sesión")
    return " ".join(map(quote, args))


def startup_enabled(config_directory):
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_RUN) as key:
                return bool(winreg.QueryValueEx(key, NAME)[0])
        except FileNotFoundError:
            return False
    return linux_startup_path(config_directory).is_file()


def set_startup(config_directory, entrypoint, enabled):
    args = [*command_line(entrypoint), "--background"]
    if sys.platform == "win32":
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_RUN) as key:
            if enabled:
                winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(args))
            else:
                try:
                    winreg.DeleteValue(key, NAME)
                except FileNotFoundError:
                    pass
    elif sys.platform.startswith("linux"):
        path = linux_startup_path(config_directory)
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("[Desktop Entry]\nType=Application\nName=Market Intelligence AI\n"
                            f"Exec={desktop_exec(args)}\nTerminal=false\n", encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
