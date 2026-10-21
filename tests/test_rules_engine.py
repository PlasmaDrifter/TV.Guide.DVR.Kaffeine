from kaffeine_dvr.dbus_client import KaffeineDbusClient
from kaffeine_dvr.rules_engine import RulesEngine, is_sports_program


def test_rules_crud(isolated_config, isolated_guide_svc, isolated_queue_mgr):
    dbus = KaffeineDbusClient()
    re = RulesEngine(isolated_config, dbus, isolated_guide_svc, isolated_queue_mgr)

    # 1. Add rule
    rule = re.add_rule("NFL Football", channel="FOX 10.1", buffer_mins=45)
    assert rule["title_keyword"] == "NFL Football"
    assert rule["channel"] == "FOX 10.1"
    assert rule["buffer_mins"] == 45
    assert rule["enabled"] is True
    assert len(re.get_rules()) == 1

    # 2. Toggle rule
    rule_id = rule["id"]
    re.toggle_rule(rule_id, False)
    assert re.get_rules()[0]["enabled"] is False

    # 3. Update rule
    re.update_rule(rule_id, "NFL Sunday", channel="All", enabled=True, buffer_mins=60)
    updated = re.get_rules()[0]
    assert updated["title_keyword"] == "NFL Sunday"
    assert updated["channel"] == "All"
    assert updated["buffer_mins"] == 60

    # 4. Remove rule
    re.remove_rule(rule_id)
    assert len(re.get_rules()) == 0

def test_is_sports_program():
    prog1 = {"show_title": "NFL Football", "episode_title": "", "summary": ""}
    prog2 = {"show_title": "Local News", "episode_title": "", "summary": ""}
    assert is_sports_program(prog1) is True
    assert is_sports_program(prog2) is False


def test_sports_buffer_threshold_over_91_minutes(isolated_config, isolated_guide_svc, isolated_queue_mgr):
    from unittest.mock import MagicMock

    from kaffeine_dvr.guide_service import get_program_duration_mins

    # 1. get_program_duration_mins parsing
    assert get_program_duration_mins({"duration_iso": "00:30:00"}) == 30
    assert get_program_duration_mins({"duration_iso": "01:00:00"}) == 60
    assert get_program_duration_mins({"duration_iso": "01:31:00"}) == 91
    assert get_program_duration_mins({"duration_iso": "01:32:00"}) == 92
    assert get_program_duration_mins({"runtime_mins": 120}) == 120
    assert get_program_duration_mins({}) == 0

    # 2. Rules engine evaluation with sports buffer
    isolated_config.auto_buffer_sports = True
    isolated_config.sports_buffer_mins = 45
    isolated_config.end_buffer_mins = 0

    re = RulesEngine(isolated_config, MagicMock(), isolated_guide_svc, isolated_queue_mgr)
    re.add_rule("Sports", channel="All", buffer_mins=None)

    # 30-minute sports talk show / preshow (<= 91 mins) -> standard buffer (0)
    preshow = {
        "show_title": "SportsWrap With Jason Page",
        "episode_title": "",
        "summary": "Sports discussion and analysis",
        "kaffeine_channel": "SUNS",
        "start_iso": "2026-10-18T18:00:00",
        "duration_iso": "00:30:00",
        "start_time_local": "2026-10-18 06:00 PM",
    }
    re.guide_service.search_programs = MagicMock(return_value=[preshow])
    scheduled = re.evaluate_and_schedule()
    assert len(scheduled) == 1
    queue_items = isolated_queue_mgr.list_queue()
    assert queue_items[0]["buffer_mins"] == 0

    # 120-minute live sports game (> 91 mins) -> sports buffer (45)
    live_game = {
        "show_title": "Sports Basketball",
        "episode_title": "Suns vs Lakers",
        "summary": "Live NBA basketball action",
        "kaffeine_channel": "SUNS",
        "start_iso": "2026-10-18T19:00:00",
        "duration_iso": "02:00:00",
        "start_time_local": "2026-10-18 07:00 PM",
    }
    re.guide_service.search_programs = MagicMock(return_value=[live_game])
    scheduled_game = re.evaluate_and_schedule()
    assert len(scheduled_game) == 1
    queue_items_2 = isolated_queue_mgr.list_queue()
    game_rec = next(x for x in queue_items_2 if x["id"] == scheduled_game[0]["id"])
    assert game_rec["buffer_mins"] == 45


def test_rules_protected_flag_and_propagation(isolated_config, isolated_guide_svc, isolated_queue_mgr):
    from unittest.mock import MagicMock

    dbus = KaffeineDbusClient()
    re = RulesEngine(isolated_config, dbus, isolated_guide_svc, isolated_queue_mgr)

    # 1. Add rule with protected=True
    rule = re.add_rule("The Conners", channel="ABC 15.1", buffer_mins=5, protected=True)
    assert rule["title_keyword"] == "The Conners"
    assert rule["channel"] == "ABC 15.1"
    assert rule["protected"] is True

    # 2. Toggle protection
    new_state = re.toggle_rule_protected(rule["id"])
    assert new_state is False
    assert re.get_rules()[0]["protected"] is False

    new_state = re.toggle_rule_protected(rule["id"], protected=True)
    assert new_state is True
    assert re.get_rules()[0]["protected"] is True

    # 3. Update rule preserves or changes protected
    re.update_rule(rule["id"], "The Conners", channel="All", enabled=True, buffer_mins=0, protected=True)
    assert re.get_rules()[0]["protected"] is True

    # 4. Evaluate rule schedules recordings with protected=1
    episode = {
        "show_title": "The Conners",
        "episode_title": "Season Finale",
        "summary": "The family gathers for a special occasion.",
        "kaffeine_channel": "ABC 15.1",
        "start_iso": "2026-10-19T20:00:00",
        "duration_iso": "00:30:00",
        "start_time_local": "2026-10-19 08:00 PM",
    }
    re.guide_service.search_programs = MagicMock(return_value=[episode])
    scheduled = re.evaluate_and_schedule()
    assert len(scheduled) == 1
    assert scheduled[0]["protected"] is True

    queued = isolated_queue_mgr.list_queue()
    assert len(queued) == 1
    assert queued[0]["title"] == "The Conners - Season Finale"
    assert queued[0]["protected"] == 1

    # 5. Existing unprotected queue item is upgraded when evaluated against a protected rule
    isolated_queue_mgr.toggle_protected(queued[0]["id"])
    assert isolated_queue_mgr.get_recording(queued[0]["id"])["protected"] == 0

    re.evaluate_and_schedule()
    assert isolated_queue_mgr.get_recording(queued[0]["id"])["protected"] == 1


def test_get_matching_programs_for_rule(isolated_config, isolated_guide_svc, isolated_queue_mgr):
    from unittest.mock import MagicMock

    dbus = KaffeineDbusClient()
    re = RulesEngine(isolated_config, dbus, isolated_guide_svc, isolated_queue_mgr)

    rule = {"title_keyword": "Suns", "channel": "SUNS", "buffer_mins": 15, "protected": True}

    prog1 = {
        "show_title": "Phoenix Suns at Portland Trail Blazers",
        "episode_title": "",
        "summary": "NBA Regular Season",
        "kaffeine_channel": "SUNS",
        "start_iso": "2026-10-21T19:00:00",
        "duration_iso": "02:30:00",
        "start_time_local": "2026-10-21 07:00 PM",
    }
    prog2 = {
        "show_title": "Golden State Warriors at Phoenix Suns",
        "episode_title": "",
        "summary": "NBA Regular Season",
        "kaffeine_channel": "SUNS",
        "start_iso": "2026-10-24T18:00:00",
        "duration_iso": "02:30:00",
        "start_time_local": "2026-10-24 06:00 PM",
    }
    prog_other = {
        "show_title": "Late Night News",
        "episode_title": "",
        "summary": "Local headlines",
        "kaffeine_channel": "SUNS",
        "start_iso": "2026-10-21T23:00:00",
        "duration_iso": "00:30:00",
        "start_time_local": "2026-10-21 11:00 PM",
    }

    re.guide_service.search_programs = MagicMock(return_value=[prog2, prog1, prog_other])

    matches = re.get_matching_programs_for_rule(rule)
    assert len(matches) == 2
    # Verify sorted chronologically
    assert matches[0]["title"] == "Phoenix Suns at Portland Trail Blazers"
    assert matches[0]["start_iso"] == "2026-10-21T19:00:00"
    assert matches[0]["buffer_mins"] == 15
    assert matches[0]["protected"] is True

    assert matches[1]["title"] == "Golden State Warriors at Phoenix Suns"
    assert matches[1]["start_iso"] == "2026-10-24T18:00:00"


def test_remove_rule_cancels_scheduled_recordings(isolated_config, isolated_guide_svc, isolated_queue_mgr):
    from unittest.mock import MagicMock

    dbus = KaffeineDbusClient()
    re = RulesEngine(isolated_config, dbus, isolated_guide_svc, isolated_queue_mgr)

    rule = re.add_rule("Suns", channel="SUNS", buffer_mins=15)
    prog = {
        "show_title": "Phoenix Suns at Portland Trail Blazers",
        "episode_title": "",
        "summary": "NBA Regular Season",
        "kaffeine_channel": "SUNS",
        "start_iso": "2026-10-21T19:00:00",
        "duration_iso": "02:30:00",
        "start_time_local": "2026-10-21 07:00 PM",
    }
    re.guide_service.search_programs = MagicMock(return_value=[prog])

    # Schedule the program
    scheduled = re.evaluate_and_schedule()
    assert len(scheduled) == 1
    queue_items = isolated_queue_mgr.list_queue()
    assert len(queue_items) == 1
    assert queue_items[0]["title"] == "Phoenix Suns at Portland Trail Blazers"

    # Now remove the rule
    cancelled = re.remove_rule(rule["id"], cancel_scheduled=True)
    assert len(cancelled) == 1
    assert len(re.get_rules()) == 0

    # Verify recording queue is now empty
    queue_items_after = isolated_queue_mgr.list_queue()
    assert len(queue_items_after) == 0



