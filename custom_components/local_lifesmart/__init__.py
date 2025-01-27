"""The LifeSmart Local integration.

This module provides the core functionality for the LifeSmart Local integration in Home Assistant. It handles the setup and configuration of the integration, as well as managing the connection to the LifeSmart API.
"""
"""The LifeSmart Local integration."""
import asyncio
import logging
import voluptuous as vol
from typing import Any, Dict, List
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN, PLATFORMS ,API_TIMEOUT
from .api import LifeSmartAPI
from requests.exceptions import RequestException
from aiohttp.client_exceptions import ClientError
from json.decoder import JSONDecodeError
from .coordinator import LifeSmartCoordinator

_LOGGER = logging.getLogger(__name__)

class LifeSmartConfigError(Exception):
    """Exception raised for errors in configuration."""
    pass

class LifeSmartConnectionError(Exception):
    """Exception raised for connection-related errors."""
    pass

class LifeSmartPlatformError(Exception):
    """Exception raised for platform-related errors."""
    pass

class LifeSmartAPIManager:
    """Class to manage LifeSmart API lifecycle."""
    
    def __init__(self, host: str, model: str, token: str, timeout: int = API_TIMEOUT):
        """Initialize the API manager."""
        self.api: LifeSmartAPI = None
        self.host = host
        self.model = model
        self.token = token
        self.timeout = timeout
        self.max_retries = 3
        self.retry_delay = 2

    async def _retry_operation(self, operation, *args, **kwargs):
        """Retry an operation with exponential backoff."""
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                return await operation(*args, **kwargs)
            except (RequestException, JSONDecodeError, ConnectionError) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    _LOGGER.debug("Attempt %d failed, retrying in %d seconds: %s", 
                                  attempt + 1, delay, str(e))
                    await asyncio.sleep(delay)
        raise last_exception

    async def initialize(self) -> LifeSmartAPI:
        """Initialize and return the API instance."""
        try:
            async def _init():
                self.api = LifeSmartAPI(
                    host=self.host,
                    model=self.model,
                    token=self.token,
                    timeout=self.timeout
                )
                return self.api
            
            return await self._retry_operation(_init)
        except RequestException as e:
            raise LifeSmartConnectionError(f"Network error while initializing LifeSmart API: {str(e)}")
        except JSONDecodeError as e:
            raise LifeSmartConnectionError(f"Invalid JSON response from LifeSmart API: {str(e)}")
        except ValueError as e:
            raise LifeSmartConfigError(f"Invalid configuration values for LifeSmart API: {str(e)}")
        except ConnectionError as e:
            raise LifeSmartConnectionError(f"Failed to connect to LifeSmart device: {str(e)}")

    async def cleanup(self):
        """Cleanup API resources."""
        if self.api:
            try:
                if hasattr(self.api, 'async_close') and callable(getattr(self.api, 'async_close')):
                    await self._retry_operation(self.api.async_close)
                elif hasattr(self.api, 'close') and callable(getattr(self.api, 'close')):
                    await self._retry_operation(self.api.close)
            except Exception as e:
                _LOGGER.debug("Error during API cleanup: %s", str(e))
            finally:
                self.api = None

def _validate_config(entry: ConfigEntry) -> bool:
    """Validate the configuration entry."""
    required_fields = ["host", "model", "token"]
    for field in required_fields:
        if not entry.data.get(field):
            _LOGGER.error("Missing required configuration field: %s", field)
            raise LifeSmartConfigError(f"Missing required configuration field: {field}")
        if not isinstance(entry.data[field], str):
            _LOGGER.error("Configuration field %s must be a string", field)
            raise LifeSmartConfigError(f"Configuration field {field} must be a string")
    return True

async def _setup_platform(hass: HomeAssistant, entry: ConfigEntry, platforms: List[str]) -> bool:
    """Set up platforms for LifeSmart integration."""
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            _LOGGER.debug("Setting up platforms (attempt %d/%d)", 
                          attempt + 1, max_retries)
            await hass.config_entries.async_forward_entry_setups(entry, platforms)
            _LOGGER.info("Successfully set up platforms")
            return True
        except ClientError as e:
            if attempt == max_retries - 1:
                _LOGGER.error("Network error while setting up platforms: %s", str(e))
                raise LifeSmartConnectionError(f"Network error while setting up platforms: {str(e)}")
            delay = retry_delay * (2 ** attempt)
            _LOGGER.debug("Retrying platform setup in %d seconds", delay)
            await asyncio.sleep(delay)
        except ImportError as e:
            _LOGGER.error("Platforms not found: %s", str(e))
            raise LifeSmartPlatformError(f"Platforms not found: {str(e)}")
        except RuntimeError as e:
            _LOGGER.error("Runtime error while setting up platforms: %s", str(e))
            raise LifeSmartPlatformError(f"Runtime error while setting up platforms: {str(e)}")

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LifeSmart Local from a config entry."""
    _LOGGER.debug("Starting LifeSmart integration setup")
    _LOGGER.debug("Config entry data: %s", entry.data)
    
    try:
        _validate_config(entry)
    except LifeSmartConfigError as e:
        _LOGGER.error("Configuration error: %s", str(e))
        return False

    api_manager = LifeSmartAPIManager(
        host=entry.data["host"],
        model=entry.data["model"],
        token=entry.data["token"]
    )

    try:
        api = await api_manager.initialize()
        _LOGGER.debug("LifeSmart API instance created")
    except (LifeSmartConnectionError, LifeSmartConfigError) as e:
        _LOGGER.error("Failed to initialize API: %s", str(e))
        return False

    coordinator = LifeSmartCoordinator(
        hass,
        api=api,
        scan_interval=1
    )

    # await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api_manager": api_manager,
        "coordinator": coordinator
    }
    _LOGGER.debug("API manager and coordinator stored in hass.data")

    # Platform setup with retry mechanism
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            _LOGGER.debug("Setting up platforms (attempt %d/%d)", attempt + 1, max_retries)
            await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
            _LOGGER.info("Successfully set up platforms")
            break
        except Exception as e:
            if attempt == max_retries - 1:
                _LOGGER.error("Failed to set up platforms: %s", str(e))
                return False
            delay = retry_delay * (2 ** attempt)
            _LOGGER.debug("Retrying platform setup in %d seconds", delay)
            await asyncio.sleep(delay)

    _LOGGER.debug("All platforms setup completed")
    return True


async def _async_unload_platforms(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload platforms for the integration."""
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            unload_results = await asyncio.gather(
                *[
                    hass.config_entries.async_forward_entry_unload(entry, platform)
                    for platform in PLATFORMS
                ]
            )
            for platform, result in zip(PLATFORMS, unload_results):
                _LOGGER.info("Platform %s unload %s", platform, "successful" if result else "failed")
            return all(unload_results)
        except Exception as e:
            if attempt == max_retries - 1:
                raise LifeSmartPlatformError(f"Error unloading platforms: {str(e)}")
            delay = retry_delay * (2 ** attempt)
            _LOGGER.debug("Retrying platform unload in %d seconds", delay)
            await asyncio.sleep(delay)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading LifeSmart integration")
    
    try:
        unload_ok: bool = await _async_unload_platforms(hass, entry)
        _LOGGER.info("Platforms unload completed with status: %s", "success" if unload_ok else "failed")
        
        if unload_ok and entry.entry_id in hass.data[DOMAIN]:
            api_manager: LifeSmartAPIManager = hass.data[DOMAIN][entry.entry_id]["api_manager"]
            coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
            
            _LOGGER.info("Cleaning up API instance and coordinator for entry_id: %s", entry.entry_id)
            await api_manager.cleanup()
            await coordinator.async_shutdown()
        
        if unload_ok:
            hass.data[DOMAIN].pop(entry.entry_id)
            _LOGGER.info("Removed entry_id %s from domain data", entry.entry_id)
            if not hass.data[DOMAIN]:
                hass.data.pop(DOMAIN)
                _LOGGER.info("Removed empty domain data")
                
        return unload_ok
    except KeyError as e:
        raise LifeSmartConfigError(f"Entry data not found in hass.data: {str(e)}")
    except RuntimeError as e:
        raise LifeSmartPlatformError(f"Runtime error while unloading entry: {str(e)}")

def generate_entity_id(device_type, hub_id, device_id, idx=None):
    """Generate entity id from device information."""
    if idx:
        return f"{device_type}_{hub_id}_{device_id}_{idx}".lower()
    return f"{device_type}_{hub_id}_{device_id}".lower()

async def send_keys(hass: HomeAssistant, call) -> None:
    """Handle send_keys service calls."""
    device_id = call.data.get("device_id")
    keys = call.data.get("keys")
    
    for entry_id, data in hass.data[DOMAIN].items():
        try:
            await data["api_manager"].api.send_keys(device_id, keys)
            _LOGGER.info(f"Successfully sent keys to device {device_id}")
            return
        except Exception as e:
            _LOGGER.error(f"Failed to send keys to device {device_id}: {str(e)}")
            raise