from pathlib import Path

from kaffeine_dvr.dbus_client import KaffeineDbusClient


def test_get_display_env_sanitizes_appimage_variables(monkeypatch):
    """
    Verify that _get_display_env properly scrubs AppImage mounts, PyInstaller internal
    directories, and leaked Qt6 plugin paths so external binaries link against system libraries.
    """
    client = KaffeineDbusClient()

    # Simulate an active AppImage execution environment
    fake_mount = "/tmp/.mount_TV.Gui123456"
    fake_appdir = fake_mount
    fake_ld = f"{fake_mount}/usr/bin/_internal:{fake_mount}/usr/lib:/usr/local/lib"
    fake_path = f"{fake_mount}/usr/bin:/usr/bin:/bin"

    monkeypatch.setenv("APPDIR", fake_appdir)
    monkeypatch.setenv("APPIMAGE", "/home/test/AppImages/app.AppImage")
    monkeypatch.setenv("ARGV0", "kaffeine-dvr")
    monkeypatch.setenv("OWD", "/home/test")
    monkeypatch.setenv("LD_LIBRARY_PATH", fake_ld)
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", fake_ld)
    monkeypatch.setenv("PATH", fake_path)
    monkeypatch.setenv("PATH_ORIG", fake_path)
    monkeypatch.setenv("PYTHONHOME", f"{fake_mount}/usr")
    monkeypatch.setenv("PYTHONPATH", f"{fake_mount}/usr/lib/python3.14")
    monkeypatch.setenv("QT_PLUGIN_PATH", f"{fake_mount}/usr/bin/_internal/PyQt6/Qt6/plugins")
    monkeypatch.setenv("QML2_IMPORT_PATH", f"{fake_mount}/usr/bin/_internal/PyQt6/Qt6/qml")
    monkeypatch.setenv("QT_QUICK_CONTROLS_CONF", f"{fake_mount}/qtquickcontrols2.conf")

    env = client._get_display_env()

    # 1. AppImage metadata must be stripped
    for var in ("APPDIR", "APPIMAGE", "ARGV0", "OWD", "LD_LIBRARY_PATH_ORIG", "PATH_ORIG", "PYTHONHOME", "PYTHONPATH"):
        assert var not in env, f"Variable {var} should be stripped from environment"

    # 2. LD_LIBRARY_PATH must exclude AppImage mount and _internal, but retain clean system libraries
    assert "LD_LIBRARY_PATH" in env
    assert fake_mount not in env["LD_LIBRARY_PATH"]
    assert "_internal" not in env["LD_LIBRARY_PATH"]
    assert env["LD_LIBRARY_PATH"] == "/usr/local/lib"

    # 3. PATH must exclude AppImage mount and retain standard paths + ~/.local/bin
    assert fake_mount not in env["PATH"]
    assert "/usr/bin" in env["PATH"]
    assert str(Path.home() / ".local" / "bin") in env["PATH"]

    # 4. Qt6 plugin / QML paths pointing into AppImage must be stripped
    assert "QT_PLUGIN_PATH" not in env
    assert "QML2_IMPORT_PATH" not in env
    assert "QT_QUICK_CONTROLS_CONF" not in env

    # 5. Essential display and KDE variables must be present
    assert env.get("DISPLAY") == ":0" or "DISPLAY" in env
    assert env.get("XDG_CURRENT_DESKTOP") == "KDE"
    assert env.get("QT_QPA_PLATFORM") == "xcb"
    assert env.get("QT_QPA_PLATFORMTHEME") == "kde"


def test_get_display_env_removes_ld_library_path_if_only_appimage_paths(monkeypatch):
    """
    Verify that if LD_LIBRARY_PATH only contained AppImage directories,
    the variable is removed completely rather than left empty.
    """
    client = KaffeineDbusClient()

    fake_mount = "/tmp/.mount_TV.GuiABCDEF"
    monkeypatch.setenv("APPDIR", fake_mount)
    monkeypatch.setenv("LD_LIBRARY_PATH", f"{fake_mount}/usr/bin/_internal:{fake_mount}/usr/lib")

    env = client._get_display_env()
    assert "LD_LIBRARY_PATH" not in env


def test_gui_main_initializes_fusion_style_and_restores_env(monkeypatch):
    """Verify gui.main sets QT_STYLE_OVERRIDE=Fusion for QApplication startup and restores it afterward."""
    import os
    import sys

    import kaffeine_dvr.gui as gui_mod

    observed = {}

    class DummyApp:
        def __init__(self, argv):
            observed["style_during_init"] = os.environ.get("QT_STYLE_OVERRIDE")

        def installEventFilter(self, filt):
            pass

        def removeEventFilter(self, filt):
            pass

        def setApplicationName(self, name):
            pass

        def setApplicationDisplayName(self, name):
            pass

        def setDesktopFileName(self, name):
            pass

        def setWindowIcon(self, icon):
            pass

        def exec(self):
            return 0

    class DummyWindow:
        def show(self):
            pass

    monkeypatch.setattr(sys, "argv", ["kaffeine-dvr"])
    monkeypatch.setattr(gui_mod, "QApplication", DummyApp)
    monkeypatch.setattr(gui_mod, "ensure_desktop_launcher", lambda: None)
    monkeypatch.setattr(gui_mod, "ensure_systemd_service", lambda: True)
    monkeypatch.setattr(gui_mod, "NoWheelEventFilter", lambda app: object())
    monkeypatch.setattr(gui_mod, "get_app_icon", lambda: object())
    monkeypatch.setattr(gui_mod, "setup_dark_theme", lambda app: None)
    monkeypatch.setattr(gui_mod, "MainWindow", DummyWindow)
    monkeypatch.setattr(os, "_exit", lambda code: None)

    monkeypatch.delenv("QT_STYLE_OVERRIDE", raising=False)
    gui_mod.main()
    assert observed["style_during_init"] == "Fusion"
    assert "QT_STYLE_OVERRIDE" not in os.environ

    monkeypatch.setenv("QT_STYLE_OVERRIDE", "Breeze")
    gui_mod.main()
    assert observed["style_during_init"] == "Fusion"
    assert os.environ.get("QT_STYLE_OVERRIDE") == "Breeze"
