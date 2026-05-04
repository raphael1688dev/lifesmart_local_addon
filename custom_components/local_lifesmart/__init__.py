"""The LifeSmart Local integration."""
import logging
import re
import socket
from datetime import timedelta
import voluptuous as vol
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval
from .const import DOMAIN, PLATFORMS, API_TIMEOUT
from .api import LifeSmartAPI

_LOGGER = logging.getLogger(__name__)

def _get_local_ip_for_target(target_ip: str) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((target_ip, 1))
        return sock.getsockname()[0]
    finally:
        sock.close()

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LifeSmart Local from a config entry."""
    api = LifeSmartAPI(
        host=entry.data["host"],
        model=entry.data["model"],
        token=entry.data["token"],
        timeout=API_TIMEOUT,
        local_port=entry.data.get("local_port", 0),
    )
    try:
        await api.async_start()
        discovery = await api.discover_devices()
    except Exception as err:
        await api.async_stop()
        raise ConfigEntryNotReady from err

    domain_data = hass.data.setdefault(DOMAIN, {"entries": {}, "_services_registered": False})
    devices = []
    if isinstance(discovery, dict) and isinstance(discovery.get("msg"), list):
        devices = discovery["msg"]
    domain_data["entries"][entry.entry_id] = {"api": api, "devices": devices}

    _async_register_services(hass)

    local_ip = await hass.async_add_executor_job(_get_local_ip_for_target, entry.data["host"])
    try:
        await api.configure_event_service(local_ip, api.local_port)
    except Exception:
        _LOGGER.warning("Failed to configure OpenDev event service (cfg:notify)")

    async def _refresh_notify(_now) -> None:
        try:
            await api.configure_event_service(local_ip, api.local_port)
        except Exception:
            _LOGGER.debug("Failed to refresh OpenDev event service (cfg:notify)")

    unsub_notify = async_track_time_interval(hass, _refresh_notify, timedelta(seconds=90))
    domain_data["entries"][entry.entry_id]["unsub_notify"] = unsub_notify

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_data = hass.data[DOMAIN]
        entry_data = domain_data["entries"].pop(entry.entry_id, None)
        if entry_data and entry_data.get("unsub_notify"):
            entry_data["unsub_notify"]()
        api: LifeSmartAPI = entry_data["api"] if entry_data else None
        if api is not None:
            await api.async_stop()
        if not domain_data["entries"]:
            hass.data.pop(DOMAIN)
    return unload_ok

def _async_register_services(hass: HomeAssistant) -> None:
    domain_data = hass.data.setdefault(DOMAIN, {"entries": {}, "_services_registered": False})
    if domain_data["_services_registered"]:
        return

    async def _handle_send_keys(call: ServiceCall) -> None:
        remote_id = call.data["remote_id"]
        keys = call.data["keys"]
        if isinstance(keys, str):
            keys_to_send = [keys]
        else:
            keys_to_send = list(keys)

        for entry_data in hass.data.get(DOMAIN, {}).get("entries", {}).values():
            api = entry_data.get("api")
            if isinstance(api, LifeSmartAPI):
                for key in keys_to_send:
                    await api.send_remote_key(remote_id, key)

    hass.services.async_register(
        DOMAIN,
        "send_keys",
        _handle_send_keys,
        schema=vol.Schema(
            {
                vol.Required("remote_id"): str,
                vol.Required("keys"): vol.Any(str, [str]),
            }
        ),
    )

    domain_data["_services_registered"] = True

def generate_entity_id(device_type, hub_id, device_id, idx=None):
    if idx:
        raw_id = f"{device_type}_{hub_id}_{device_id}_{idx}".lower()
    else:
        raw_id = f"{device_type}_{hub_id}_{device_id}".lower()
    return re.sub(r"_+", "_", raw_id).strip("_")
