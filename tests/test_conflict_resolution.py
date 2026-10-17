from datetime import datetime, timedelta
from unittest.mock import MagicMock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog

from kaffeine_dvr.config import ConfigManager
from kaffeine_dvr.gui import MainWindow, RecordingConflictDialog
from kaffeine_dvr.queue_manager import QueueManager


def test_find_scheduling_conflicts_single_tuner(isolated_queue_mgr: QueueManager):
    qm = isolated_queue_mgr
    t_start_a = "2026-10-17T10:00:00"
    dur_a = "00:30:00"  # ends at 10:30:00

    # Queue Show A on SUNS
    id_a = qm.add_recording(
        title="Speak of the Devils",
        channel="SUNS",
        start_iso=t_start_a,
        duration_iso=dur_a,
        buffer_mins=0
    )

    # 1. No conflict on same channel (even if times overlap)
    conflicts_same_ch = qm.find_scheduling_conflicts(
        channel="SUNS",
        start_iso="2026-10-17T10:25:00",
        duration_iso="00:30:00",
        total_tuners=1
    )
    assert len(conflicts_same_ch) == 0

    # 2. No conflict when times do not overlap
    conflicts_no_overlap = qm.find_scheduling_conflicts(
        channel="Outlaw",
        start_iso="2026-10-17T10:30:00",
        duration_iso="00:30:00",
        total_tuners=1
    )
    assert len(conflicts_no_overlap) == 0

    # 3. Conflict detected on different channel overlapping 10:25 to 10:30 (5 mins)
    conflicts = qm.find_scheduling_conflicts(
        channel="Outlaw",
        start_iso="2026-10-17T10:25:00",
        duration_iso="00:30:00",
        total_tuners=1
    )
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["recording"]["id"] == id_a
    assert c["recording"]["channel"] == "SUNS"
    assert c["overlap_mins"] == 5
    assert c["conflict_type"] == "preceding_overlaps_start"
    assert c["earlier_rec"] == "existing"
    assert c["cut_early_end_iso"] == "2026-10-17T10:24:55"
    assert c["cut_early_dur_iso"] == "00:24:55"
    assert c["delay_start_iso"] == "2026-10-17T10:30:00"
    assert c["delay_dur_iso"] == "00:25:00"


def test_find_scheduling_conflicts_multi_tuner(isolated_queue_mgr: QueueManager):
    qm = isolated_queue_mgr

    # Queue Show A on SUNS (10:00–10:30)
    qm.add_recording(
        title="Show on SUNS",
        channel="SUNS",
        start_iso="2026-10-17T10:00:00",
        duration_iso="00:30:00"
    )

    # With 2 tuners available, scheduling Outlaw (10:25–10:55) should NOT conflict because tuner 2 is free
    conflicts_2tuners = qm.find_scheduling_conflicts(
        channel="Outlaw",
        start_iso="2026-10-17T10:25:00",
        duration_iso="00:30:00",
        total_tuners=2
    )
    assert len(conflicts_2tuners) == 0

    # Queue Show B on CBS (10:00–10:30) - now 2 tuners are occupied
    qm.add_recording(
        title="Show on CBS",
        channel="CBS",
        start_iso="2026-10-17T10:00:00",
        duration_iso="00:30:00"
    )

    # Now with 2 tuners occupied, scheduling a 3rd channel (Outlaw) at 10:25 causes a conflict
    conflicts_busy = qm.find_scheduling_conflicts(
        channel="Outlaw",
        start_iso="2026-10-17T10:25:00",
        duration_iso="00:30:00",
        total_tuners=2
    )
    assert len(conflicts_busy) >= 1


def test_trim_recording_end(isolated_queue_mgr: QueueManager):
    qm = isolated_queue_mgr
    rec_id = qm.add_recording(
        title="Full Show",
        channel="SUNS",
        start_iso="2026-10-17T10:00:00",
        duration_iso="00:30:00",
        buffer_mins=5
    )

    success = qm.trim_recording_end(
        queue_id=rec_id,
        new_end_iso="2026-10-17T10:24:55",
        new_dur_iso="00:24:55"
    )
    assert success is True

    item = [r for r in qm.list_queue() if r["id"] == rec_id][0]
    assert item["end_iso"] == "2026-10-17T10:24:55"
    assert item["duration_iso"] == "00:24:55"
    assert item["buffer_mins"] == 0


def test_delay_recording_start(isolated_queue_mgr: QueueManager):
    qm = isolated_queue_mgr
    rec_id = qm.add_recording(
        title="Show to Delay",
        channel="Outlaw",
        start_iso="2026-10-17T10:25:00",
        duration_iso="00:30:00"
    )

    success = qm.delay_recording_start(
        queue_id=rec_id,
        new_start_iso="2026-10-17T10:30:00",
        new_dur_iso="00:25:00"
    )
    assert success is True

    item = [r for r in qm.list_queue() if r["id"] == rec_id][0]
    assert item["start_iso"] == "2026-10-17T10:30:00"
    assert item["duration_iso"] == "00:25:00"


def test_recording_conflict_dialog_widgets_and_actions(qtbot):
    conflict = {
        "recording": {
            "id": 1,
            "title": "Speak of the Devils",
            "channel": "SUNS",
            "start_iso": "2026-10-17T10:00:00",
            "end_iso": "2026-10-17T10:30:00"
        },
        "overlap_mins": 5,
        "conflict_type": "preceding_overlaps_start",
        "earlier_rec": "existing",
        "cut_early_end_iso": "2026-10-17T10:24:55",
        "cut_early_dur_iso": "00:24:55",
        "delay_start_iso": "2026-10-17T10:30:00",
        "delay_dur_iso": "00:25:00"
    }

    dlg = RecordingConflictDialog(
        conflict=conflict,
        requested_title="The Roy Rogers Show",
        requested_channel="Outlaw",
        requested_start_iso="2026-10-17T10:25:00",
        requested_duration_iso="00:30:00",
        total_tuners=1
    )
    qtbot.addWidget(dlg)

    # Default is trim_preceding
    assert dlg.trim_radio.isChecked()
    dlg._on_confirm()
    assert dlg.get_resolution() == "trim_preceding"

    # Switch to delay_upcoming
    dlg.delay_radio.setChecked(True)
    dlg._on_confirm()
    assert dlg.get_resolution() == "delay_upcoming"

    # Switch to cancel
    dlg.cancel_radio.setChecked(True)
    dlg._on_confirm()
    assert dlg.get_resolution() == "cancel"


def test_record_selected_guide_item_conflict_trim(qtbot, isolated_config: ConfigManager, isolated_queue_mgr: QueueManager):
    win = MainWindow()
    qtbot.addWidget(win)
    win.config_mgr = isolated_config
    win.queue_mgr = isolated_queue_mgr
    win.watcher.queue_mgr = isolated_queue_mgr

    base_time = datetime.now() + timedelta(days=1)
    t_suns = base_time.replace(hour=10, minute=0, second=0, microsecond=0)
    t_outlaw = base_time.replace(hour=10, minute=25, second=0, microsecond=0)

    # Pre-populate conflicting recording on SUNS (10:00–10:30)
    id_suns = isolated_queue_mgr.add_recording(
        title="Speak of the Devils",
        channel="SUNS",
        start_iso=t_suns.strftime("%Y-%m-%dT%H:%M:%S"),
        duration_iso="00:30:00",
        buffer_mins=0
    )

    prog_outlaw = {
        "show_title": "The Roy Rogers Show",
        "episode_title": "The Train Robbery",
        "kaffeine_channel": "Outlaw",
        "start_iso": t_outlaw.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration_iso": "00:30:00",
        "_category": "tvshows"
    }

    # Simulate user choosing 'trim_preceding' in dialog
    def mock_conflict_dialog(*args, **kwargs):
        dlg = MagicMock()
        dlg.exec.return_value = QDialog.DialogCode.Accepted
        dlg.get_resolution.return_value = "trim_preceding"
        return dlg

    import kaffeine_dvr.gui
    orig_dialog = kaffeine_dvr.gui.RecordingConflictDialog
    kaffeine_dvr.gui.RecordingConflictDialog = mock_conflict_dialog

    try:
        win.record_selected_guide_item(prog_outlaw)

        queue = isolated_queue_mgr.list_queue()
        assert len(queue) == 2

        # SUNS recording should be trimmed to end 5s before Outlaw starts
        expected_suns_end = (t_outlaw - timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%S")
        suns_rec = [r for r in queue if r["id"] == id_suns][0]
        assert suns_rec["end_iso"] == expected_suns_end
        assert suns_rec["duration_iso"] == "00:24:55"

        # Outlaw recording should start at 10:25:00
        outlaw_rec = [r for r in queue if r["channel"] == "Outlaw"][0]
        assert outlaw_rec["start_iso"] == t_outlaw.strftime("%Y-%m-%dT%H:%M:%S")
    finally:
        kaffeine_dvr.gui.RecordingConflictDialog = orig_dialog


def test_record_selected_guide_item_conflict_delay(qtbot, isolated_config: ConfigManager, isolated_queue_mgr: QueueManager):
    win = MainWindow()
    qtbot.addWidget(win)
    win.config_mgr = isolated_config
    win.queue_mgr = isolated_queue_mgr
    win.watcher.queue_mgr = isolated_queue_mgr

    base_time = datetime.now() + timedelta(days=1)
    t_suns = base_time.replace(hour=10, minute=0, second=0, microsecond=0)
    t_outlaw = base_time.replace(hour=10, minute=25, second=0, microsecond=0)

    id_suns = isolated_queue_mgr.add_recording(
        title="Speak of the Devils",
        channel="SUNS",
        start_iso=t_suns.strftime("%Y-%m-%dT%H:%M:%S"),
        duration_iso="00:30:00",
        buffer_mins=0
    )

    prog_outlaw = {
        "show_title": "The Roy Rogers Show",
        "episode_title": "The Train Robbery",
        "kaffeine_channel": "Outlaw",
        "start_iso": t_outlaw.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration_iso": "00:30:00",
        "_category": "tvshows"
    }

    # Simulate user choosing 'delay_upcoming' in dialog
    def mock_conflict_dialog(*args, **kwargs):
        dlg = MagicMock()
        dlg.exec.return_value = QDialog.DialogCode.Accepted
        dlg.get_resolution.return_value = "delay_upcoming"
        return dlg

    import kaffeine_dvr.gui
    orig_dialog = kaffeine_dvr.gui.RecordingConflictDialog
    kaffeine_dvr.gui.RecordingConflictDialog = mock_conflict_dialog

    try:
        win.record_selected_guide_item(prog_outlaw)

        queue = isolated_queue_mgr.list_queue()
        assert len(queue) == 2

        # SUNS recording runs until 10:30:00 (with automatic 5s handover margin for Outlaw)
        expected_suns_end = (t_suns + timedelta(minutes=30) - timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%S")
        suns_rec = [r for r in queue if r["id"] == id_suns][0]
        assert suns_rec["end_iso"] == expected_suns_end
        assert suns_rec["duration_iso"] == "00:29:55"

        # Outlaw recording should start at 10:30:00 with reduced duration (25m)
        expected_outlaw_start = (t_suns + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")
        outlaw_rec = [r for r in queue if r["channel"] == "Outlaw"][0]
        assert outlaw_rec["start_iso"] == expected_outlaw_start
        assert outlaw_rec["duration_iso"] == "00:25:00"
    finally:
        kaffeine_dvr.gui.RecordingConflictDialog = orig_dialog


def test_record_selected_guide_item_conflict_cancel(qtbot, isolated_config: ConfigManager, isolated_queue_mgr: QueueManager):
    win = MainWindow()
    qtbot.addWidget(win)
    win.config_mgr = isolated_config
    win.queue_mgr = isolated_queue_mgr
    win.watcher.queue_mgr = isolated_queue_mgr

    base_time = datetime.now() + timedelta(days=1)
    t_suns = base_time.replace(hour=10, minute=0, second=0, microsecond=0)
    t_outlaw = base_time.replace(hour=10, minute=25, second=0, microsecond=0)

    id_suns = isolated_queue_mgr.add_recording(
        title="Speak of the Devils",
        channel="SUNS",
        start_iso=t_suns.strftime("%Y-%m-%dT%H:%M:%S"),
        duration_iso="00:30:00",
        buffer_mins=0
    )

    prog_outlaw = {
        "show_title": "The Roy Rogers Show",
        "episode_title": "The Train Robbery",
        "kaffeine_channel": "Outlaw",
        "start_iso": t_outlaw.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration_iso": "00:30:00",
        "_category": "tvshows"
    }

    # Simulate user choosing 'cancel' in dialog
    def mock_conflict_dialog(*args, **kwargs):
        dlg = MagicMock()
        dlg.exec.return_value = QDialog.DialogCode.Rejected
        dlg.get_resolution.return_value = "cancel"
        return dlg

    import kaffeine_dvr.gui
    orig_dialog = kaffeine_dvr.gui.RecordingConflictDialog
    kaffeine_dvr.gui.RecordingConflictDialog = mock_conflict_dialog

    try:
        win.record_selected_guide_item(prog_outlaw)

        queue = isolated_queue_mgr.list_queue()
        # Only the original SUNS recording should exist
        assert len(queue) == 1
        assert queue[0]["id"] == id_suns
        assert queue[0]["duration_iso"] == "00:30:00"
    finally:
        kaffeine_dvr.gui.RecordingConflictDialog = orig_dialog


def test_guide_grid_horizontal_headers_left_aligned(qtbot, isolated_config: ConfigManager):
    win = MainWindow(config_mgr=isolated_config)
    qtbot.addWidget(win)

    table = win.guide_grid_table
    assert table.columnCount() > 0
    for col in range(min(5, table.columnCount())):
        item = table.horizontalHeaderItem(col)
        assert item is not None
        assert item.textAlignment() == (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)


