"""Sensor platform for Liiga Goalie Statistics."""
from __future__ import annotations

import logging
from typing import Any, Dict
from datetime import datetime

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, LiigaGoalieStatsDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Category-specific formatting and icons
CATEGORY_CONFIG = {
    "savepercentage": {
        "name": "Save Percentage",
        "icon": "mdi:shield-check",
        "value_suffix": "%",
        "precision": 1
    },
    "shutouts": {
        "name": "Shutouts",
        "icon": "mdi:shield-lock",
        "value_suffix": "",
        "precision": 0
    },
    "goalsagainstavg": {
        "name": "Goals Against Avg",
        "icon": "mdi:hockey-puck",
        "value_suffix": "",
        "precision": 2
    },
    "wins": {
        "name": "Wins",
        "icon": "mdi:trophy",
        "value_suffix": "",
        "precision": 0
    },
    "losses": {
        "name": "Losses",
        "icon": "mdi:emoticon-sad",
        "value_suffix": "",
        "precision": 0
    },
    "ties": {
        "name": "Ties",
        "icon": "mdi:handshake",
        "value_suffix": "",
        "precision": 0
    },
    "saves": {
        "name": "Saves",
        "icon": "mdi:shield",
        "value_suffix": "",
        "precision": 0
    },
    "xgea": {
        "name": "Expected Goals Effect",
        "icon": "mdi:chart-line",
        "value_suffix": "",
        "precision": 2
    },
    "games": {
        "name": "Games",
        "icon": "mdi:calendar-check",
        "value_suffix": "",
        "precision": 0
    }
}

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN]["coordinator"]
    
    sensors = []
    for category in coordinator.categories:
        sensors.append(LiigaGoalieStatsLeaderboardSensor(coordinator, category))
    
    async_add_entities(sensors, True)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    sensors = []
    for category in coordinator.categories:
        sensors.append(LiigaGoalieStatsLeaderboardSensor(coordinator, category))
    
    async_add_entities(sensors, True)

class LiigaGoalieStatsLeaderboardSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Liiga Goalie Leaderboard sensor."""

    def __init__(
        self, coordinator: LiigaGoalieStatsDataUpdateCoordinator, category: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.category = category
        
        # Get category config or use defaults
        category_config = CATEGORY_CONFIG.get(category, {
            "name": category.capitalize(),
            "icon": "mdi:hockey-puck",
            "value_suffix": "",
            "precision": 0
        })
        
        self._attr_name = f"Liiga Goalie {category_config['name']} Leaders"
        self._attr_unique_id = f"liigagoalies_{category}_leaderboard"
        self._attr_icon = category_config["icon"]
        self.value_suffix = category_config["value_suffix"]
        self.precision = category_config["precision"]

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        if not self.coordinator.data or self.category not in self.coordinator.data:
            return "Unknown"
        
        # Get the name of the top goalie in this category
        leaders = self.coordinator.data.get(self.category, [])
        if not leaders:
            return "No data"
        
        return leaders[0].get("name", "Unknown")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        if not self.coordinator.data or self.category not in self.coordinator.data:
            return {}
        
        leaders = self.coordinator.data.get(self.category, [])
        
        # Format leaderboard data
        formatted_leaders = []
        for goalie in leaders:
            # Format the value according to category precision
            if self.precision == 0:
                formatted_value = f"{int(goalie.get('value', 0))}{self.value_suffix}"
            else:
                formatted_value = f"{goalie.get('value', 0):.{self.precision}f}{self.value_suffix}"
                
            formatted_leaders.append({
                "rank": goalie.get("rank", 0),
                "name": goalie.get("name", "Unknown"),
                "team": goalie.get("team", "Unknown"),
                "value": formatted_value,
                "games": goalie.get("games", 0),
                "position": goalie.get("position", ""),
                "number": goalie.get("number", ""),
                "image_url": goalie.get("image_url", ""),
                "wins": goalie.get("wins", 0),
                "losses": goalie.get("losses", 0),
                "ties": goalie.get("ties", 0),
                "record": f"{goalie.get('wins', 0)}-{goalie.get('losses', 0)}-{goalie.get('ties', 0)}"
            })
        
        # Extract image URL for the leader (for convenient access)
        leader_image_url = leaders[0].get("image_url", "") if leaders else ""
        
        return {
            "leaders": formatted_leaders,
            "last_updated": self.coordinator.last_update_success_time.isoformat() if self.coordinator.last_update_success_time else None,
            "category": self.category,
            "category_name": CATEGORY_CONFIG.get(self.category, {}).get("name", self.category.capitalize()),
            "leader_image_url": leader_image_url
        }
