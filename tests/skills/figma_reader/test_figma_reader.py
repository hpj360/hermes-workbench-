"""Tests for figma-reader Skill"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).parent.parent.parent.parent / "skills" / "figma-reader"
SCRIPTS = SKILL_DIR / "scripts"

# 让 import 找得到 client
sys.path.insert(0, str(SCRIPTS))


class TestFigmaClient:
    def test_mock_mode_with_fixture(self):
        from client import FigmaClient
        client = FigmaClient(mock=True)
        result = client.get_file("ABC")
        assert "name" in result
        assert result["name"] == "Mock Design System"

    def test_mock_components(self):
        from client import FigmaClient
        client = FigmaClient(mock=True)
        result = client.get_components("ABC")
        assert "meta" in result
        assert len(result["meta"]["components"]) >= 1

    def test_mock_images(self):
        from client import FigmaClient
        client = FigmaClient(mock=True)
        result = client.get_images("ABC", ["1:2"], fmt="png", scale=2.0)
        assert "images" in result
        assert "1:2" in result["images"]

    def test_invalid_format_raises(self):
        from client import FigmaClient
        client = FigmaClient(mock=True)
        with pytest.raises(ValueError, match="fmt 必须是"):
            client.get_images("ABC", ["1:2"], fmt="gif")


class TestParseUrl:
    def test_file_url(self):
        from parse_url import parse_figma_url
        result = parse_figma_url("https://www.figma.com/file/ABC123/My-File?node-id=1-2")
        assert result["file_key"] == "ABC123"
        assert result["node_id"] == "1:2"

    def test_design_url(self):
        from parse_url import parse_figma_url
        result = parse_figma_url("https://www.figma.com/design/XYZ789/Page?node-id=3%3A4")
        assert result["file_key"] == "XYZ789"
        assert result["node_id"] == "3:4"

    def test_invalid_url_raises(self):
        from parse_url import parse_figma_url
        with pytest.raises(ValueError):
            parse_figma_url("https://example.com/not-figma")

    def test_invalid_path_raises(self):
        from parse_url import parse_figma_url
        with pytest.raises(ValueError):
            parse_figma_url("https://www.figma.com/garbage/ABC")
