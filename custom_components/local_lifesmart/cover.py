"""Platform for LifeSmart cover integration."""
import logging
from typing import Optional
from homeassistant.components.cover import CoverEntity, CoverDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN, CMD_SET
from . import generate_entity_id

_LOGGER = logging.getLogger(__name__)
PORT_1 = "P2"
PORT_2 = "P3"
PORT_3 = "P4"
TYPE_ON= 0x81
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    _LOGGER.debug("Setting up LifeSmart cover platform")
    entry_data = hass.data[DOMAIN]["entries"][config_entry.entry_id]
    api = entry_data["api"]
    devices = entry_data.get("devices") or []
    if not devices:
        devices_data = await api.discover_devices()
        if isinstance(devices_data, dict) and isinstance(devices_data.get("msg"), list):
            devices = devices_data["msg"]
            entry_data["devices"] = devices
    
    covers = []
    if isinstance(devices, list):
        _LOGGER.debug("Found %s devices in response", len(devices))
        for device in devices:
            if device.get("devtype") == "SL_P":
                _LOGGER.debug("Adding cover device: %s", device.get('name', 'MINS Curtain'))
                covers.append(
                    LifeSmartCover(
                        api=api,
                        device=device,
                        idx=device.get('idx', 0)
                    )
                )
    
    _LOGGER.debug("Adding %s cover entities", len(covers))
    async_add_entities(covers)

class LifeSmartCover(CoverEntity):
    """Representation of a LifeSmart cover."""
    _attr_should_poll = False
    def __init__(self, api, device, idx: Optional[str] = None):
        self._api = api
        self._device = device
        self._attr_name = device.get('name', 'MINS Curtain')
        self._attr_unique_id = f"lifesmart_cover_{device['me']}"
        self._attr_device_class = CoverDeviceClass.CURTAIN
        self._attr_is_closed = None
        self._idx = idx
        device_type = device.get("devtype")
        hub_id = device.get("agt", "")
        device_id = device["me"]
        self.entity_id = f"cover.{generate_entity_id(device_type, hub_id, device_id, idx)}"

        _LOGGER.debug("Initializing cover: %s (ID: %s)", self._attr_name, self._attr_unique_id)
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device['me'])},
            name=device.get('name', 'LifeSmart Curtain'),
            manufacturer="LifeSmart",
            model=device.get('devtype', 'SL_P'),
            sw_version=device.get('epver', 'Unknown')
        )

    async def async_open_cover(self, **kwargs):
        """Open the cover."""
        _LOGGER.debug("Opening cover: %s", self._attr_name)
        await self._api.send_command("ep", {
            "me": self._device["me"],
            "idx": PORT_1,
            "type": TYPE_ON,
            "val": 1
        }, CMD_SET)

    async def async_close_cover(self, **kwargs):
        """Close the cover."""
        _LOGGER.debug("Closing cover: %s", self._attr_name)
        await self._api.send_command("ep", {
            "me": self._device["me"],
            "idx": PORT_2,
            "type": 0x81,
            "val": 0
        }, CMD_SET)

    async def async_stop_cover(self, **kwargs):
        """Stop the cover."""
        _LOGGER.debug("Stopping cover: %s", self._attr_name)
        await self._api.send_command("ep", {
            "me": self._device["me"],
            "idx": PORT_3,
            "type": 0x81,
            "val": 0
        }, CMD_SET)
