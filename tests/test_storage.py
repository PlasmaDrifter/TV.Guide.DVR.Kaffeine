from pathlib import Path

from kaffeine_dvr.storage_manager import StorageManager


def test_storage_find_recorded_files(tmp_path: Path, isolated_config, isolated_queue_mgr):
    rec_dir = tmp_path / "recordings"
    rec_dir.mkdir()

    # Create dummy files
    f1 = rec_dir / "movie1.m2t"
    f2 = rec_dir / "show2.ts"
    f3 = rec_dir / "readme.txt"
    f1.write_bytes(b"x" * 1024)
    f2.write_bytes(b"y" * 2048)
    f3.write_bytes(b"z" * 100)

    sm = StorageManager(isolated_config, isolated_queue_mgr)
    found = sm.find_recorded_files(folder=rec_dir)

    # Only video files (.m2t, .ts) should be picked up
    names = [f["name"] for f in found]
    assert "movie1.m2t" in names
    assert "show2.ts" in names
    assert "readme.txt" not in names


def test_check_history_file_availability(tmp_path: Path, isolated_config, isolated_queue_mgr):
    rec_dir = tmp_path / "recordings"
    rec_dir.mkdir()
    isolated_config.custom_recording_folder = str(rec_dir)

    sm = StorageManager(isolated_config, isolated_queue_mgr)

    # 1. Non-existent file
    entry1 = {"title": "Missing Show", "start_iso": "2026-10-15T10:00:00", "file_path": str(rec_dir / "missing.m2t")}
    avail1, path1, sz1 = sm.check_history_file_availability(entry1)
    assert not avail1
    assert path1 is None
    assert sz1 == 0

    # 2. Existing file with exact path recorded
    video2 = rec_dir / "Movie_20261015.m2t"
    video2.write_bytes(b"A" * 50000)
    entry2 = {"title": "Movie", "start_iso": "2026-10-15T10:00:00", "file_path": str(video2)}
    avail2, path2, sz2 = sm.check_history_file_availability(entry2)
    assert avail2
    assert path2 == video2
    assert sz2 == 50000

    # 3. Existing file discovered in directory by matching title and date
    video3 = rec_dir / "Evening News_2026-10-15.ts"
    video3.write_bytes(b"B" * 80000)
    entry3 = {"title": "Evening News", "start_iso": "2026-10-15T18:00:00", "file_path": None}
    avail3, path3, sz3 = sm.check_history_file_availability(entry3)
    assert avail3
    assert path3 == video3
    assert sz3 == 80000


def test_mark_file_purged_clears_queue_and_history(isolated_queue_mgr):
    qm = isolated_queue_mgr

    # 1. Add unprotected history entry with file_path
    h1 = qm.add_history_entry(
        title="Show One",
        channel="NBC",
        start_iso="2026-10-18T10:00:00",
        duration_iso="00:30:00",
        file_path="/fake/path/Show One.m2t",
        protected=0
    )

    # 2. Add protected history entry with file_path
    h2 = qm.add_history_entry(
        title="Protected Show",
        channel="CBS",
        start_iso="2026-10-18T11:00:00",
        duration_iso="00:30:00",
        file_path="/fake/path/Protected Show.m2t",
        protected=1
    )

    # 3. Add unprotected queue item
    conn = qm._get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO recording_queue (title, channel, start_iso, duration_iso, end_iso, status, file_path, protected)
        VALUES ('Show One', 'NBC', '2026-10-18T10:00:00', '00:30:00', '2026-10-18T10:30:00', 'COMPLETED', '/fake/path/Show One.m2t', 0)
    """)
    conn.commit()
    conn.close()

    # Verify both are present in history
    hist = qm.list_history()
    assert any(h["id"] == h1 for h in hist)
    assert any(h["id"] == h2 for h in hist)

    # Purge unprotected file
    qm.mark_file_purged("/fake/path/Show One.m2t")

    # Verify unprotected history row was deleted
    hist_after = qm.list_history()
    assert not any(h["id"] == h1 for h in hist_after)

    # Verify protected history row was NOT deleted
    assert any(h["id"] == h2 for h in hist_after)

    # Verify queue entry was deleted
    queue_after = qm.list_queue(include_completed=True)
    assert not any(q["title"] == "Show One" for q in queue_after)


def test_cleanup_cycle_reloads_config(tmp_path: Path, isolated_config, isolated_queue_mgr):
    import json
    import time
    rec_dir = tmp_path / "recordings"
    rec_dir.mkdir()
    isolated_config.custom_recording_folder = str(rec_dir)
    isolated_config.auto_cleanup_enabled = False

    sm = StorageManager(isolated_config, isolated_queue_mgr)

    # Initial check - auto_cleanup is False
    res1 = sm.run_cleanup_cycle()
    assert res1["enabled"] is False

    # Simulate UI setting auto_cleanup_enabled = True and min_free_disk_gb = 500
    with open(isolated_config.config_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["auto_cleanup_enabled"] = True
    data["min_free_disk_gb"] = 500
    time.sleep(0.05)
    with open(isolated_config.config_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

    # Calling run_cleanup_cycle should automatically reload config and proceed
    res2 = sm.run_cleanup_cycle()
    assert res2["enabled"] is True


