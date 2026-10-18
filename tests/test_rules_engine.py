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

