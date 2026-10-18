from datetime import datetime
from unittest.mock import MagicMock, patch

from kaffeine_dvr.config import ConfigManager
from kaffeine_dvr.queue_manager import QueueManager
from kaffeine_dvr.watcher import Watcher


def test_recover_interrupted_recording_success(isolated_queue_mgr: QueueManager, isolated_config: ConfigManager):
    now = datetime(2026, 10, 17, 10, 30, 0)
    start_iso = "2026-10-17T10:00:00"
    end_iso = "2026-10-17T11:00:00"

    qid = isolated_queue_mgr.add_recording(
        title="Interrupted Show",
        channel="Nosey",
        start_iso=start_iso,
        duration_iso="01:00:00",
        buffer_mins=0
    )
    isolated_queue_mgr.mark_armed(qid, 55)
    conn = isolated_queue_mgr._get_connection()
    conn.execute("UPDATE recording_queue SET status = 'RECORDING' WHERE id = ?", (qid,))
    conn.commit()
    conn.close()

    mock_dbus = MagicMock()
    mock_dbus.is_running.return_value = False
    mock_dbus.schedule_recording.return_value = 101

    watcher = Watcher(dbus_client=mock_dbus, queue_mgr=isolated_queue_mgr, config_mgr=isolated_config)

    with patch("kaffeine_dvr.watcher.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.fromisoformat = datetime.fromisoformat

        recovered = watcher.recover_interrupted_recordings()
        assert recovered == 1

    mock_dbus.schedule_recording.assert_called_once_with(
        "Interrupted Show", "Nosey", "2026-10-17T10:30:00", "00:30:00", 0
    )

    rec = isolated_queue_mgr.get_recording(qid)
    assert rec["kaffeine_key"] == 101
    assert rec["status"] == "RECORDING"
    assert rec["start_iso"] == start_iso  # original start preserved for guide grid matching
    assert rec["end_iso"] == end_iso


def test_recover_interrupted_recording_under_5_mins_bypassed(isolated_queue_mgr: QueueManager, isolated_config: ConfigManager):
    # Only 4 minutes remaining (10:26:00 to 10:30:00)
    now = datetime(2026, 10, 17, 10, 26, 0)
    start_iso = "2026-10-17T10:00:00"

    qid = isolated_queue_mgr.add_recording(
        title="Ending Soon",
        channel="Nosey",
        start_iso=start_iso,
        duration_iso="00:30:00",
        buffer_mins=0
    )
    isolated_queue_mgr.mark_armed(qid, 56)

    mock_dbus = MagicMock()
    mock_dbus.is_running.return_value = False

    watcher = Watcher(dbus_client=mock_dbus, queue_mgr=isolated_queue_mgr, config_mgr=isolated_config)

    with patch("kaffeine_dvr.watcher.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.fromisoformat = datetime.fromisoformat

        recovered = watcher.recover_interrupted_recordings()
        assert recovered == 0

    mock_dbus.schedule_recording.assert_not_called()


def test_recover_interrupted_recording_running_stream_ignored(isolated_queue_mgr: QueueManager, isolated_config: ConfigManager):
    now = datetime(2026, 10, 17, 10, 30, 0)
    start_iso = "2026-10-17T10:00:00"

    qid = isolated_queue_mgr.add_recording(
        title="Already Active Show",
        channel="Nosey",
        start_iso=start_iso,
        duration_iso="01:00:00",
        buffer_mins=0
    )
    isolated_queue_mgr.mark_armed(qid, 77)

    mock_dbus = MagicMock()
    mock_dbus.is_running.return_value = True
    # D-Bus reports stream 77 is already running
    mock_dbus._list_via_dbus.return_value = [
        {"id": 77, "name": "Already Active Show", "channel": "Nosey", "is_running": True}
    ]

    watcher = Watcher(dbus_client=mock_dbus, queue_mgr=isolated_queue_mgr, config_mgr=isolated_config)

    with patch("kaffeine_dvr.watcher.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.fromisoformat = datetime.fromisoformat

        recovered = watcher.recover_interrupted_recordings()
        assert recovered == 0

    mock_dbus.schedule_recording.assert_not_called()


def test_recover_interrupted_recording_tuner_conflict_capping(isolated_queue_mgr: QueueManager, isolated_config: ConfigManager):
    now = datetime(2026, 10, 17, 10, 30, 0)

    # Show A on Nosey (10:00 - 11:00)
    qid_a = isolated_queue_mgr.add_recording(
        title="Show A",
        channel="Nosey",
        start_iso="2026-10-17T10:00:00",
        duration_iso="01:00:00",
        buffer_mins=0
    )
    isolated_queue_mgr.mark_armed(qid_a, 10)

    # Show B on ABC starting at 10:45:00 (15 minutes from now)
    isolated_queue_mgr.add_recording(
        title="Show B",
        channel="ABC",
        start_iso="2026-10-17T10:45:00",
        duration_iso="00:30:00",
        buffer_mins=0
    )

    mock_dbus = MagicMock()
    mock_dbus.is_running.return_value = False
    mock_dbus.schedule_recording.return_value = 102

    watcher = Watcher(dbus_client=mock_dbus, queue_mgr=isolated_queue_mgr, config_mgr=isolated_config)

    with patch("kaffeine_dvr.watcher.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.fromisoformat = datetime.fromisoformat

        recovered = watcher.recover_interrupted_recordings()
        assert recovered == 1

    # Remaining duration must stop 5s early for Show B (10:45:00 - 5s = 10:44:55 -> 14m 55s)
    mock_dbus.schedule_recording.assert_called_once_with(
        "Show A", "Nosey", "2026-10-17T10:30:00", "00:14:55", 0
    )


def test_recover_interrupted_recording_prevent_duplicate_loops(isolated_queue_mgr: QueueManager, isolated_config: ConfigManager):
    now = datetime(2026, 10, 17, 10, 30, 0)

    qid = isolated_queue_mgr.add_recording(
        title="Once Only Show",
        channel="Nosey",
        start_iso="2026-10-17T10:00:00",
        duration_iso="01:00:00",
        buffer_mins=0
    )
    isolated_queue_mgr.mark_armed(qid, 20)

    mock_dbus = MagicMock()
    mock_dbus.is_running.return_value = False
    mock_dbus.schedule_recording.return_value = 103

    watcher = Watcher(dbus_client=mock_dbus, queue_mgr=isolated_queue_mgr, config_mgr=isolated_config)

    with patch("kaffeine_dvr.watcher.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.fromisoformat = datetime.fromisoformat

        first_pass = watcher.recover_interrupted_recordings()
        assert first_pass == 1

        # Second pass in same session
        second_pass = watcher.recover_interrupted_recordings()
        assert second_pass == 0

    assert mock_dbus.schedule_recording.call_count == 1
