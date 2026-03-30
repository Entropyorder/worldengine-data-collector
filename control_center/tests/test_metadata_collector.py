import json
import pytest
from unittest.mock import patch
from metadata_collector import build_systeminfo, detect_perspective, build_game_meta_dict


class TestBuildSystemInfo:
    def test_returns_required_keys(self):
        mock_rect = (0, 0, 1920, 1080)
        with patch("metadata_collector.get_game_window_rect", return_value=mock_rect), \
             patch("metadata_collector.get_system_dpi", return_value=1.0), \
             patch("metadata_collector.get_process_title", return_value="Valheim"):
            info = build_systeminfo("valheim", 1920, 1080)
        assert info["gameProcessName"] == "Valheim"
        assert info["width"] == 1920
        assert info["height"] == 1080
        assert info["recordDpi"] == 1.0
        assert info["window_rect"] == [{"x": 0, "y": 0}, {"x": 1920, "y": 1080}]

    def test_dpi_rounds_to_one_decimal(self):
        with patch("metadata_collector.get_game_window_rect", return_value=(0, 0, 1920, 1080)), \
             patch("metadata_collector.get_system_dpi", return_value=1.4999), \
             patch("metadata_collector.get_process_title", return_value="Valheim"):
            info = build_systeminfo("valheim", 1920, 1080)
        assert info["recordDpi"] == round(1.4999, 1)


class TestDetectPerspective:
    def test_small_offset_is_first_person(self):
        offsets = [[0.0, 0.1, 0.0]] * 100
        assert detect_perspective(offsets) == "第一人称"

    def test_large_offset_is_third_person(self):
        offsets = [[0.5, 2.5, -5.0]] * 100
        assert detect_perspective(offsets) == "第三人称"


class TestBuildGameMetaDict:
    def test_returns_required_keys(self):
        game_cfg = {
            "game_name": "Valheim",
            "game_meta": {"game_type_description": "探索游戏", "perspective": "第三人称"},
            "key_mapping": {87: "前进(W)"},
            "mouse_config": {"description": "鼠标控制视角"},
        }
        sample_offsets = [[0.5, 2.5, -5.0]] * 10
        result = build_game_meta_dict(game_cfg, sample_offsets, width=1920, height=1080)
        assert result["游戏类型描述"] == "探索游戏"
        assert result["视角配置"] == "第三人称"
        assert result["画面分辨率"] == "1920x1080"
        assert "键盘映射规则" in result
        assert "相机位置是否固定" in result
        assert "相机位置描述" in result
        assert "鼠标对应规则" in result
