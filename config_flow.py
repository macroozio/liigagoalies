"""Config flow for Liiga Goalie Statistics integration."""
import logging
from typing import Any, Dict, Optional

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEFAULT_URL = "https://liiga.fi/api/v2/players/stats/summed/2025/2025/runkosarja/true?dataType=basicStatsGk"
DEFAULT_CATEGORIES = "savepercentage,shutouts,goalsagainstavg"

DATA_SCHEMA = vol.Schema(
    {
        vol.Required("url", default=DEFAULT_URL): str,
        vol.Optional("categories", default=DEFAULT_CATEGORIES): str,
        vol.Optional("top_n", default=5): int,
    }
)

async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)
    
    try:
        async with session.get(data["url"]) as resp:
            if resp.status != 200:
                raise CannotConnect(f"Invalid response from API: {resp.status}")
            
            # Try to parse JSON
            await resp.json()
            
    except aiohttp.ClientError as err:
        raise CannotConnect(f"Error connecting: {err}")
    except ValueError:
        raise InvalidData("Invalid JSON data returned from API")
    
    # Return info to be stored in the config entry
    return {"title": "Liiga Goalie Stats"}

class LiigaGoaliesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Liiga Goalie Statistics."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                
                # Process categories from comma-separated string to list
                categories = [c.strip() for c in user_input["categories"].split(",")]
                user_input["categories"] = categories
                
                return self.async_create_entry(title=info["title"], data=user_input)
            
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidData:
                errors["base"] = "invalid_data"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
        
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

class InvalidData(HomeAssistantError):
    """Error to indicate invalid data was received."""
