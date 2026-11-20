# -*- coding: utf-8 -*-
"""Jinja2 globals and filters for DOTA_MASTER templates."""

import os
import re
from typing import Dict

from .icons import item_img_url, ability_img_url, item_name, neutral_item_name, hero_item_name

from analysis.hero_strategies import (get_counter_heroes, get_primary_counter,
                                       counter_note)


# Hero slug mapping for portrait URLs
HERO_SLUG_MAP: Dict[str, str] = {
    'Abaddon': 'abaddon',
    'Alchemist': 'alchemist',
    'Ancient Apparition': 'ancient_apparition',
    'Anti-Mage': 'antimage',
    'Arc Warden': 'arc_warden',
    'Axe': 'axe',
    'Bane': 'bane',
    'Batrider': 'batrider',
    'Beastmaster': 'beastmaster',
    'Bloodseeker': 'bloodseeker',
    'Bounty Hunter': 'bounty_hunter',
    'Brewmaster': 'brewmaster',
    'Bristleback': 'bristleback',
    'Broodmother': 'broodmother',
    'Centaur Warrunner': 'centaur',
    'Chaos Knight': 'chaos_knight',
    'Chen': 'chen',
    'Clinkz': 'clinkz',
    'Clockwerk': 'rattletrap',
    'Crystal Maiden': 'crystal_maiden',
    'Dark Seer': 'dark_seer',
    'Dark Willow': 'dark_willow',
    'Dawnbreaker': 'dawnbreaker',
    'Dazzle': 'dazzle',
    'Death Prophet': 'death_prophet',
    'Disruptor': 'disruptor',
    'Doom': 'doom_bringer',
    'Dragon Knight': 'dragon_knight',
    'Drow Ranger': 'drow_ranger',
    'Earth Spirit': 'earth_spirit',
    'Earthshaker': 'earthshaker',
    'Elder Titan': 'elder_titan',
    'Ember Spirit': 'ember_spirit',
    'Enchantress': 'enchantress',
    'Enigma': 'enigma',
    'Faceless Void': 'faceless_void',
    'Grimstroke': 'grimstroke',
    'Gyrocopter': 'gyrocopter',
    'Hoodwink': 'hoodwink',
    'Huskar': 'huskar',
    'Invoker': 'invoker',
    'Io': 'wisp',
    'Jakiro': 'jakiro',
    'Juggernaut': 'juggernaut',
    'Keeper of the Light': 'keeper_of_the_light',
    'Keeper Of The Light': 'keeper_of_the_light',
    'Kez': 'kez',
    'Kunkka': 'kunkka',
    'Largo': 'largo',
    'Legion Commander': 'legion_commander',
    'Leshrac': 'leshrac',
    'Lich': 'lich',
    'Lifestealer': 'life_stealer',
    'Lina': 'lina',
    'Lion': 'lion',
    'Lone Druid': 'lone_druid',
    'Luna': 'luna',
    'Lycan': 'lycan',
    'Magnus': 'magnataur',
    'Marci': 'marci',
    'Mars': 'mars',
    'Medusa': 'medusa',
    'Meepo': 'meepo',
    'Mirana': 'mirana',
    'Monkey King': 'monkey_king',
    'Morphling': 'morphling',
    'Muerta': 'muerta',
    'Naga Siren': 'naga_siren',
    "Nature's Prophet": 'furion',
    'Necrophos': 'necrolyte',
    'Night Stalker': 'night_stalker',
    'Nyx Assassin': 'nyx_assassin',
    'Ogre Magi': 'ogre_magi',
    'Omniknight': 'omniknight',
    'Oracle': 'oracle',
    'Outworld Destroyer': 'obsidian_destroyer',
    'Outworld Devourer': 'obsidian_destroyer',
    'Pangolier': 'pangolier',
    'Phantom Assassin': 'phantom_assassin',
    'Phantom Lancer': 'phantom_lancer',
    'Phoenix': 'phoenix',
    'Primal Beast': 'primal_beast',
    'Puck': 'puck',
    'Pudge': 'pudge',
    'Pugna': 'pugna',
    'Queen of Pain': 'queenofpain',
    'Razor': 'razor',
    'Riki': 'riki',
    'Ringmaster': 'ringmaster',
    'Rubick': 'rubick',
    'Sand King': 'sand_king',
    'Shadow Demon': 'shadow_demon',
    'Shadow Fiend': 'nevermore',
    'Shadow Shaman': 'shadow_shaman',
    'Silencer': 'silencer',
    'Skywrath Mage': 'skywrath_mage',
    'Slardar': 'slardar',
    'Slark': 'slark',
    'Snapfire': 'snapfire',
    'Sniper': 'sniper',
    'Spectre': 'spectre',
    'Spirit Breaker': 'spirit_breaker',
    'Storm Spirit': 'storm_spirit',
    'Sven': 'sven',
    'Techies': 'techies',
    'Templar Assassin': 'templar_assassin',
    'Terrorblade': 'terrorblade',
    'Tidehunter': 'tidehunter',
    'Timbersaw': 'shredder',
    'Tinker': 'tinker',
    'Tiny': 'tiny',
    'Treant Protector': 'treant',
    'Troll Warlord': 'troll_warlord',
    'Tusk': 'tusk',
    'Underlord': 'abyssal_underlord',
    'Undying': 'undying',
    'Ursa': 'ursa',
    'Vengeful Spirit': 'vengefulspirit',
    'Venomancer': 'venomancer',
    'Viper': 'viper',
    'Visage': 'visage',
    'Void Spirit': 'void_spirit',
    'Warlock': 'warlock',
    'Weaver': 'weaver',
    'Windranger': 'windrunner',
    'Winter Wyvern': 'winter_wyvern',
    'Witch Doctor': 'witch_doctor',
    'Wraith King': 'skeleton_king',
    'Zeus': 'zuus',
}


GAME_MODES = {
    1: "All Pick",
    2: "Captains Mode",
    3: "Random Draft",
    4: "Single Draft",
    5: "All Random",
    6: "Intro",
    7: "Diretide",
    8: "Reverse Captains Mode",
    9: "Greeviling",
    10: "Tutorial",
    11: "Mid Only",
    12: "Least Played",
    13: "Limited Heroes",
    14: "Compendium",
    15: "Custom",
    16: "Captains Draft",
    17: "Balanced Draft",
    18: "Ability Draft",
    19: "Event",
    20: "All Random Deathmatch",
    21: "1v1 Mid",
    22: "All Draft",
    23: "Turbo",
    24: "Mutation",
}


def hero_slug(hero_name: str) -> str:
    """Convert hero name to slug for portrait URL."""
    if not hero_name:
        return 'unknown'
    name = hero_name.strip()
    if name in HERO_SLUG_MAP:
        return HERO_SLUG_MAP[name]
    title_name = name.title()
    if title_name in HERO_SLUG_MAP:
        return HERO_SLUG_MAP[title_name]
    slug = name.lower()
    slug = re.sub(r'[\s]+', '_', slug)
    slug = re.sub(r'[^\w_]', '', slug)
    return slug


def hero_img_url(hero_name: str, size: int = 256) -> str:
    """Return hero portrait URL — local static/heroes/ or CDN fallback."""
    slug = hero_slug(hero_name)
    local_path = os.path.join("static", "heroes", f"{slug}.png")
    if os.path.exists(local_path):
        return f"/static/heroes/{slug}.png"
    return f"https://cdn.opendota.com/heroes/{slug}.png"


def game_mode_name(gm) -> str:
    """Convert numeric game_mode to readable name."""
    if isinstance(gm, str) and not gm.isdigit():
        return gm
    try:
        return GAME_MODES.get(int(gm), f"Mode {gm}")
    except (ValueError, TypeError):
        return str(gm)


def register_jinja_globals(app) -> None:
    """Register all Jinja2 globals and filters with Flask app."""
    app.jinja_env.globals['hero_slug'] = hero_slug
    app.jinja_env.globals['hero_img_url'] = hero_img_url
    app.jinja_env.globals['item_img_url'] = item_img_url
    app.jinja_env.globals['ability_img_url'] = ability_img_url
    app.jinja_env.globals['item_name'] = item_name
    app.jinja_env.globals['neutral_item_name'] = neutral_item_name
    app.jinja_env.globals['hero_item_name'] = hero_item_name
    app.jinja_env.globals['game_mode_name'] = game_mode_name
    app.jinja_env.globals['get_counter_heroes'] = get_counter_heroes
    app.jinja_env.globals['get_primary_counter'] = get_primary_counter
    app.jinja_env.globals['counter_note'] = counter_note

    # Utility functions
    app.jinja_env.globals['max'] = lambda *args: max(*args) if args else 0
    app.jinja_env.globals['min'] = lambda *args: min(*args) if args else 0
    app.jinja_env.globals['round'] = lambda value, precision=0: round(value, precision)