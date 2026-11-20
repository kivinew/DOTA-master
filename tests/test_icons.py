# -*- coding: utf-8 -*-
"""Item icon helpers must work with OpenDota string IDs and any cwd."""

from analysis.icons import item_img_url, item_name, hero_item_name


def test_item_icon_uses_local_asset_for_string_id(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert item_img_url("1") == "/static/items/blink.png"
    assert item_name("1") == "Blink"


def test_hero_item_name_handles_string_ids_and_neutrals():
    assert hero_item_name({"id": "1"}) == "Blink"
    assert hero_item_name(("neutral", "1592")) == "Trusty Shovel"


def test_empty_item_has_no_icon_url():
    assert item_img_url(0) == ""
