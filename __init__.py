"""
Custom Home Assistant integration for Finnish Liiga hockey goalie statistics.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta, datetime
import aiohttp

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

DOMAIN = "liigagoalies"
SCAN_INTERVAL = timedelta(hours=1)  # Update hourly - Liiga stats don't change that often

# Configuration schema for configuration.yaml
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required("url"): cv.string,
                vol.Optional("categories", default=["savepercentage", "shutouts", "goalsagainstavg"]): vol.All(
                    cv.ensure_list, [cv.string]
                ),
                vol.Optional("top_n", default=5): cv.positive_int,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

PLATFORMS = ["sensor"]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Liiga Goalie Stats component."""
    if DOMAIN not in config:
        return True

    hass.data[DOMAIN] = {}
    
    url = config[DOMAIN]["url"]
    categories = config[DOMAIN]["categories"]
    top_n = config[DOMAIN]["top_n"]
    
    coordinator = LiigaGoalieStatsDataUpdateCoordinator(
        hass, url=url, categories=categories, top_n=top_n
    )
    
    await coordinator.async_refresh()
    
    hass.data[DOMAIN]["coordinator"] = coordinator
    
    for platform in PLATFORMS:
        hass.async_create_task(
            hass.helpers.discovery.async_load_platform(
                platform, DOMAIN, {}, config
            )
        )
    
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Liiga Goalie Stats from a config entry."""
    url = entry.data["url"]
    categories = entry.data.get("categories", ["savepercentage", "shutouts", "goalsagainstavg"])
    top_n = entry.data.get("top_n", 5)
    
    coordinator = LiigaGoalieStatsDataUpdateCoordinator(
        hass, url=url, categories=categories, top_n=top_n
    )
    
    await coordinator.async_refresh()
    
    if not coordinator.last_update_success:
        raise ConfigEntryNotReady
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
            ]
        )
    )
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok

class LiigaGoalieStatsDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Finnish Hockey goalie data from Liiga.fi API."""

    def __init__(
        self, hass: HomeAssistant, url: str, categories: list[str], top_n: int
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.url = url
        self.categories = categories
        self.top_n = top_n
        self.session = async_get_clientsession(hass)
        self.last_update_success_time = None

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            data = await self._fetch_data()
            if data:
                # On successful data fetch, update the timestamp
                self.last_update_success_time = datetime.now()
            return data
        except Exception as err:
            raise UpdateFailed(f"Error communicating with Liiga API: {err}")

    async def _fetch_data(self):
        """Fetch the actual data from Liiga.fi API."""
        try:
            async with self.session.get(self.url) as resp:
                if resp.status != 200:
                    _LOGGER.error("Liiga API returned status %s", resp.status)
                    return {}
                
                data = await resp.json()
                
                # Debug log to see the actual structure
                _LOGGER.debug("API Response structure: %s", type(data))
                if isinstance(data, dict):
                    _LOGGER.debug("API Response keys: %s", data.keys())
                
                return self._process_data(data)
        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching data from Liiga API: %s", err)
            return {}

    def _process_data(self, data):
        """Process the fetched data into leaderboards based on the Liiga.fi API structure for goalies."""
        result = {}
        
        # Map of our category names to API field names
        category_mapping = {
            "savepercentage": "savePercentage",
            "shutouts": "shutOut",
            "goalsagainstavg": "goalsAgainstAvg",
            "wins": "gkWins",
            "losses": "gkLosses",
            "ties": "gkTies",
            "saves": "blockedOrSavedShots",
            "xgea": "xgea",  # Expected Goals Effect for goalies
            "games": "games"
        }
        
        # Handle different API response structures
        goalies = []
        
        # Check if data contains a list of players directly or is nested
        if isinstance(data, list):
            goalies = [p for p in data if p.get('goalkeeper', False)]
        elif isinstance(data, dict) and "playerStats" in data:
            goalies = [p for p in data.get("playerStats", []) if p.get('goalkeeper', False)]
        elif isinstance(data, dict) and "players" in data:
            goalies = [p for p in data.get("players", []) if p.get('goalkeeper', False)]
        
        if not goalies:
            _LOGGER.warning("No goalie data found in API response or unrecognized format")
            _LOGGER.debug("API Response type: %s", type(data))
            return result
        
        # Create leaderboards for each category
        for category in self.categories:
            if category in category_mapping:
                api_field = category_mapping[category]
                
                # Filter out players who don't have the required field, ensure they're goalkeepers
                valid_goalies = [p for p in goalies if self._has_valid_field(p, api_field)]
                
                # For most stats, higher is better, but goals against average lower is better
                reverse_sort = category != "goalsagainstavg"
                
                # Sort goalies by the category
                sorted_goalies = sorted(
                    valid_goalies, 
                    key=lambda x: self._safe_get_value(x, api_field),
                    reverse=reverse_sort
                )
                
                # Take top N goalies
                top_goalies = []
                for i, goalie in enumerate(sorted_goalies[:self.top_n], 1):
                    full_name = f"{goalie.get('firstName', '')} {goalie.get('lastName', '')}"
                    team = goalie.get('teamName', goalie.get('teamShortName', 'Unknown'))
                    
                    top_goalies.append({
                        "rank": i,
                        "name": full_name.strip(),
                        "team": team,
                        "value": self._safe_get_value(goalie, api_field),
                        "games": goalie.get('games', 0),
                        "position": goalie.get('role', ''),
                        "number": goalie.get('jersey', ''),
                        "player_id": goalie.get('playerId', ''),
                        "image_url": goalie.get('pictureUrl', ''),
                        "wins": goalie.get('gkWins', 0),
                        "losses": goalie.get('gkLosses', 0),
                        "ties": goalie.get('gkTies', 0)
                    })
                
                # Store in result
                result[category] = top_goalies
        
        return result
    
    def _has_valid_field(self, player, field):
        """Check if player has the field and it can be converted to a number."""
        if field not in player:
            return False
            
        value = player.get(field)
        if value is None:
            return False
            
        # Try to convert to float
        try:
            if isinstance(value, str):
                float(value.replace(',', '.').replace('%', ''))
            else:
                float(value) if value is not None else 0
            return True
        except (ValueError, TypeError):
            return False
    
    def _safe_get_value(self, player, field):
        """Safely get a numeric value from player data, with appropriate type conversion."""
        value = player.get(field, 0)
        
        # Handle percentage values or string representations
        if isinstance(value, str):
            try:
                return float(value.replace(',', '.').replace('%', ''))
            except (ValueError, TypeError):
                return 0
        
        # Return 0 for None values (common in goalie stats when no games played)
        return float(value) if value is not None else 0
