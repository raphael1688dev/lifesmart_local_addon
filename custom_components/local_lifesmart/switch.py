"""
Represents a LifeSmart switch entity in Home Assistant.

The `LifeSmartSwitch` class is responsible for managing the state and behavior of a LifeSmart switch device. It handles fetching the initial state, updating the state when changes occur, and sending commands to turn the switch on or off.

The `async_setup_entry` function is responsible for setting up the LifeSmart switches when a new configuration entry is added. It discovers the available devices, creates `LifeSmartSwitch` instances for each supported switch, and adds them to Home Assistant.
"""
"""Platform for LifeSmart switch integration."""
import logging
from asyncio import Lock
import asyncio
import time

from typing import Any, Dict, List, Optional
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN, CMD_GET, CMD_SET, VAL_TYPE_ONOFF, MANUFACTURER
from . import generate_entity_id
_LOGGER = logging.getLogger(__name__)

SUPPORTED_SWITCH_TYPES = [
    "SL_SW_NS1",
    "SL_SW_NS2",
    "SL_SW_NS3",
    "SL_NATURE"
]
TYPE_ON = 0x81  # For turning on
TYPE_OFF = 0x80  # For turning off
SWITCH_CHANNELS = ["L1", "L2", "L3"]
TAG_M = "tag"
TAG_VALUE = "m"
ME = "me"
IDX = "idx"
TYPE = "type"
VAL = "val"
CODE = "code"
EP = "ep"
DATA = "data"
MSG = "msg"
DEVTYPE = "devtype"
NAME = "name"
EPVER = "epver"
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    _LOGGER.info("Setting up LifeSmart switches")
    _LOGGER.debug("Starting switch setup with config: %s", config_entry.as_dict())
    
    try:
        coordinator = hass.data[DOMAIN][config_entry.entry_id]['coordinator']
        _LOGGER.debug(f"Coordinator data: {coordinator}")
        await coordinator.async_config_entry_first_refresh()

        devices_data = await coordinator._async_update_data()
        _LOGGER.debug(f"Devices data: {devices_data}")
        
        switches: List[LifeSmartSwitch] = []
        if not devices_data:
            _LOGGER.error("No device data received from LifeSmart API")
            return

        if isinstance(devices_data, dict) and MSG in devices_data:
            _LOGGER.debug("Processing devices data: %s", devices_data)
            for device in devices_data[MSG]:
                try:
                    _LOGGER.debug("Processing device: %s", device)
                    if device.get(DEVTYPE) in SUPPORTED_SWITCH_TYPES:
                        data = device.get(DATA, {})
                        for channel in SWITCH_CHANNELS:
                            if channel in data:
                                channel_data = data[channel]
                                name = f"{device.get(NAME, 'Switch')} {channel_data.get(NAME, channel).replace('{$EPN}', '').strip()}"
                                _LOGGER.debug("Creating switch for device %s, channel %s, name %s", device.get(ME), channel, name)
                                switches.append(
                                    LifeSmartSwitch(
                                        coordinator=coordinator,
                                        device=device,
                                        idx=channel,
                                        name=name.strip()
                                    )
                                )
                except Exception as device_ex:
                    _LOGGER.error(f"Error processing device: {device.get(ME, 'unknown')}: {str(device_ex)}")
                    _LOGGER.debug("Device processing error details", exc_info=True)
                    continue

        _LOGGER.info(f"Adding {len(switches)} LifeSmart switches")
        _LOGGER.debug("Switches to be added: %s", switches)
        if switches:
            async_add_entities(switches)
        else:
            _LOGGER.debug("No supported switches found")
            
    except Exception as setup_ex:
        _LOGGER.error(f"Failed to set up LifeSmart switches: {str(setup_ex)}")
        _LOGGER.debug("Setup error details", exc_info=True)
        raise

class LifeSmartSwitch(SwitchEntity):
    """Representation of a LifeSmart switch."""
    
    def __init__(self, coordinator: Any, device: Dict[str, Any], idx: str, name: str) -> None:
        """Initialize the switch."""
        _LOGGER.debug("Initializing switch with device: %s, idx: %s, name: %s", device, idx, name)
        if not device or not isinstance(device, dict):
            raise ValueError("Invalid device data provided")
        self._lock = Lock()            
        self.coordinator = coordinator
        self._device = device
        self._idx = idx
        self._attr_name = name
        self._attr_unique_id = f"lifesmart_switch_{device.get(ME, 'unknown')}_{idx}"
        self._available = True
        device_type = device.get('devtype')
        hub_id = device.get('agt', '')
        device_id = device['me']
        self.entity_id = f"{DOMAIN}.{generate_entity_id(device_type, hub_id, device_id, idx)}"
        self._last_action_time = 0
        self._min_time_between_actions = 1  # 500ms minimum between actions
    
        try:
            initial_state = device.get(DATA, {}).get(idx, {}).get(VAL, 0)
            self._state = bool(initial_state)
            _LOGGER.debug("Initial state set to: %s for device: %s", self._state, self._attr_unique_id)
        except Exception as ex:
            _LOGGER.error(f"Error setting initial state for {name}: {str(ex)}")
            _LOGGER.debug("Initial state error details", exc_info=True)
            self._state = False
        _LOGGER.info(f"Initializing LifeSmart switch: {self._attr_name} with state: {self._state}")

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._attr_name

    @property
    def is_on(self) -> bool:
        """Return true if device is on."""
        return self._state

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available and self.coordinator.last_update_success

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device[ME])},
            name=self._attr_name,
            manufacturer=MANUFACTURER,
            model=self._device.get(DEVTYPE, 'Unknown'),
            sw_version=self._device.get(EPVER, 'Unknown'),
        )

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        _LOGGER.debug("Adding %s to Home Assistant", self._attr_unique_id)
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug("Handling coordinator update for %s", self._attr_unique_id)
        # Call an async method to handle the update
        self.hass.async_create_task(self._async_handle_update())
        
    async def _async_handle_update(self) -> None:    
        """Handle updated data from the coordinator."""
        _LOGGER.debug("Handling coordinator update for %s", self._attr_unique_id)
        async with self._lock:
            try:
                device_data = self.coordinator.data
                if device_data and MSG in device_data:
                    for device in device_data[MSG]:
                        if device.get(ME) == self._device[ME]:
                            new_state = bool(device.get(DATA, {}).get(self._idx, {}).get("v", 0))
                            _LOGGER.debug("Updating state from %s to %s for %s", self._state, new_state, self._attr_unique_id)
                            self._state = new_state
                            self._available = True
                            self.async_write_ha_state()
                            break
            except Exception as ex:
                _LOGGER.error(f"Error handling coordinator update for {self._attr_name}: {str(ex)}")
                _LOGGER.debug("Coordinator update error details", exc_info=True)
                self._available = False

    # @callback
    # def _handle_coordinator_update(self) -> None:
    #     """Handle updated data from the coordinator."""
    #     _LOGGER.debug("Handling coordinator update for %s", self._attr_unique_id)
    #     device_data = self.coordinator.data.get(MSG, [])
    #     for device in device_data:
    #         if device.get(ME) == self._device[ME]:
    #             try:
    #                 new_state = bool(device.get(DATA, {}).get(self._idx, {}).get("v", 0))  # Changed val to v
    #                 _LOGGER.debug("Updating state from %s to %s for %s", self._state, new_state, self._attr_unique_id)
    #                 self._state = new_state
    #                 self._available = True
    #                 self.async_write_ha_state()
    #             except Exception as ex:
    #                 _LOGGER.error(f"Error handling coordinator update for {self._attr_name}: {str(ex)}")
    #                 _LOGGER.debug("Coordinator update error details", exc_info=True)
    #                 self._available = False
    #             break

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        if self._state:
            return
        
        _LOGGER.debug("Turning on %s", self._attr_unique_id)
        current_time = time.time()
        if current_time - self._last_action_time < self._min_time_between_actions:
            _LOGGER.debug("Ignoring rapid switch ON action for %s", self._attr_unique_id)
            return
        self._last_action_time = current_time
        try:
            state = {
                "idx": self._idx,
                "type": TYPE_ON,
                "val": 1
            }
            await self.coordinator.async_set_device_state(
                self._device[ME],
                state
            )
            self._state = True
            self.async_write_ha_state()
                
        except Exception as ex:
            _LOGGER.error(f"Failed to turn on {self._attr_name}: {str(ex)}")
            self._state = False
            self.async_write_ha_state()
            self._available = False
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""

        _LOGGER.debug("Turning off %s", self._attr_unique_id)
        current_time = time.time()
        if current_time - self._last_action_time < self._min_time_between_actions:
            _LOGGER.debug("Ignoring rapid switch OFF action for %s", self._attr_unique_id)
            return
        self._last_action_time = current_time
        try:
            state = {
                "idx": self._idx,
                "type": TYPE_OFF,
                "val": 0
            }
            await self.coordinator.async_set_device_state(
                self._device[ME],
                state
            )
            self._state = False
            self.async_write_ha_state()
                
        except Exception as ex:
            _LOGGER.error(f"Failed to turn off {self._attr_name}: {str(ex)}")
            self._state = True
            self.async_write_ha_state()
            self._available = False
            raise
