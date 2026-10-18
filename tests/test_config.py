from kaffeine_dvr.config import DEFAULT_CATEGORY_COLORS, ConfigManager


def test_default_config(isolated_config: ConfigManager):
    cfg = isolated_config
    assert cfg.end_buffer_mins == 0
    assert cfg.sports_buffer_mins == 40
    assert cfg.auto_buffer_sports is True
    assert cfg.auto_check_updates is False
    assert cfg.update_check_frequency == "weekly"
    assert cfg.grid_visible_rows == 10
    assert cfg.guide_detail_lines == 3
    assert cfg.lead_time_mins == 10
    assert cfg.watcher_interval_seconds == 210
    assert cfg.notification_lead_time_mins == 1
    assert cfg.timeshift_buffer_seconds == 2
    assert cfg.zero_byte_recording_timeout_secs == 5
    assert cfg.guide_auto_advance_interval == 2


def test_zero_byte_timeout_clamping(isolated_config: ConfigManager):
    cfg = isolated_config
    cfg.zero_byte_recording_timeout_secs = 1
    assert cfg.zero_byte_recording_timeout_secs == 3

    cfg.zero_byte_recording_timeout_secs = 200
    assert cfg.zero_byte_recording_timeout_secs == 120

    cfg.zero_byte_recording_timeout_secs = 5
    assert cfg.zero_byte_recording_timeout_secs == 5

def test_grid_visible_rows_clamping(isolated_config: ConfigManager):
    cfg = isolated_config
    cfg.grid_visible_rows = 2
    assert cfg.grid_visible_rows == 4

    cfg.grid_visible_rows = 25
    assert cfg.grid_visible_rows == 16

    cfg.grid_visible_rows = 11
    assert cfg.grid_visible_rows == 11


def test_guide_detail_lines_clamping(isolated_config: ConfigManager):
    cfg = isolated_config
    cfg.guide_detail_lines = 1
    assert cfg.guide_detail_lines == 2

    cfg.guide_detail_lines = 5
    assert cfg.guide_detail_lines == 3

    cfg.guide_detail_lines = 2
    assert cfg.guide_detail_lines == 2

    cfg.guide_detail_lines = 3
    assert cfg.guide_detail_lines == 3

def test_reset_to_defaults_preserves_user_data(isolated_config: ConfigManager):
    cfg = isolated_config
    # Set user rules and channels
    cfg.channel_map = {"ABC": "Channel 7.1", "NBC": "Channel 12.1"}
    cfg.rules = [{"title": "My Favorite Show", "channel": "ABC"}]
    cfg.tvpassport_stations = {"ABC": 1234}

    # Change tweakable settings
    cfg.end_buffer_mins = 15
    cfg.lead_time_mins = 20
    cfg.grid_visible_rows = 12
    cfg.set_category_color("sports", "#112233")

    # Reset
    cfg.reset_to_defaults(keep_channels_and_rules=True)

    # Verify user data preserved
    assert cfg.channel_map == {"ABC": "Channel 7.1", "NBC": "Channel 12.1"}
    assert len(cfg.rules) == 1
    assert cfg.rules[0]["title"] == "My Favorite Show"
    assert cfg.tvpassport_stations == {"ABC": 1234}

    # Verify settings restored to defaults
    assert cfg.end_buffer_mins == 0
    assert cfg.lead_time_mins == 10
    assert cfg.grid_visible_rows == 10
    assert cfg.category_colors["sports"] == DEFAULT_CATEGORY_COLORS["sports"]

def test_reset_category_colors(isolated_config: ConfigManager):
    cfg = isolated_config
    cfg.set_category_color("movies", "#999999")
    assert cfg.category_colors["movies"] == "#999999"

    cfg.reset_category_colors()
    assert cfg.category_colors["movies"] == DEFAULT_CATEGORY_COLORS["movies"]


def test_settings_ui_scale_clamping(isolated_config: ConfigManager):
    cfg = isolated_config
    assert cfg.settings_ui_scale == 100

    cfg.settings_ui_scale = 50
    assert cfg.settings_ui_scale == 90

    cfg.settings_ui_scale = 250
    assert cfg.settings_ui_scale == 180

    cfg.settings_ui_scale = 125
    assert cfg.settings_ui_scale == 125


def test_custom_theme_presets_limit_and_overwrite(isolated_config: ConfigManager):
    cfg = isolated_config
    assert len(cfg.custom_theme_presets) == 0

    # Save 6 custom themes
    keys = [cfg.save_custom_theme_preset(f"Theme {i}") for i in range(1, 7)]
    k1, k2 = keys[0], keys[1]
    assert len(cfg.custom_theme_presets) == 6

    # Attempting to save a 7th should raise ValueError
    import pytest
    with pytest.raises(ValueError, match="Maximum limit of 6"):
        cfg.save_custom_theme_preset("Theme 7")

    # Overwriting an existing key replaces it and preserves the 6 limit
    k7 = cfg.save_custom_theme_preset("Theme 7 Overwrite", overwrite_key=k1)
    assert len(cfg.custom_theme_presets) == 6
    assert k1 not in cfg.custom_theme_presets
    assert k7 in cfg.custom_theme_presets
    assert cfg.custom_theme_presets[k7]["name"] == "Theme 7 Overwrite"

    # Deleting allows adding a new one
    cfg.delete_custom_theme_preset(k2)
    assert len(cfg.custom_theme_presets) == 5
    cfg.save_custom_theme_preset("Theme 8")
    assert len(cfg.custom_theme_presets) == 6


def test_unconfigured_regional_channels_respects_lineup_and_dismissal(isolated_config: ConfigManager, monkeypatch):
    cfg = isolated_config
    # Mock scanned channels from Kaffeine
    scanned = [
        {"name": "Fox", "number": 1},
        {"name": "CBS", "number": 2},
        {"name": "Local TV", "number": 3},
        {"name": "Ignored Regional", "number": 4},
        {"name": "Removed Channel", "number": 5},
    ]
    monkeypatch.setattr(cfg, "get_scanned_kaffeine_channels", lambda: scanned)

    # Active lineup in channel_map
    cfg.channel_map = {
        "Fox": "Fox",
        "CBS": "CBS",
        "Local TV": "Local TV",
        "Ignored Regional": "Ignored Regional",
    }
    # Removed Channel is NOT in channel_map

    # Configure TV Passport only for Fox & CBS (national)
    cfg.tvpassport_stations = {}

    # "Removed Channel" is not in lineup, so it should not appear
    unconfigured = cfg.get_unconfigured_regional_channels()
    assert "Removed Channel" not in unconfigured
    assert "Local TV" in unconfigured
    assert "Ignored Regional" in unconfigured

    # Dismiss "Ignored Regional"
    cfg.dismissed_regional_channels = ["Ignored Regional"]
    unconfigured_after = cfg.get_unconfigured_regional_channels()
    assert "Ignored Regional" not in unconfigured_after
    assert "Local TV" in unconfigured_after


def test_guide_auto_advance_interval_clamping(isolated_config: ConfigManager):
    cfg = isolated_config
    # Default is 2 hours
    assert cfg.guide_auto_advance_interval == 2

    # Set to 1 hour
    cfg.guide_auto_advance_interval = 1
    assert cfg.guide_auto_advance_interval == 1

    # Set to 2 hours
    cfg.guide_auto_advance_interval = 2
    assert cfg.guide_auto_advance_interval == 2

    # Set to 3 hours
    cfg.guide_auto_advance_interval = 3
    assert cfg.guide_auto_advance_interval == 3

    # Any other value defaults back to 2
    cfg.guide_auto_advance_interval = 5
    assert cfg.guide_auto_advance_interval == 2

    cfg.guide_auto_advance_interval = 0
    assert cfg.guide_auto_advance_interval == 2




