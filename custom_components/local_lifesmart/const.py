"""Config flow for LifeSmart Local integration."""
import voluptuous as vol
import logging
import ipaddress
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_TOKEN
from .const import DOMAIN, DEFAULT_MODEL
from .api import LifeSmartAPI

_LOGGER = logging.getLogger(__name__)

def validate_host(host):
    """Validate that the host is a valid IP address or hostname."""
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        if len(host) > 253 or not all(len(part) <= 63 for part in host.split(".")):
            raise vol.Invalid("Invalid hostname")
        return host

def validate_token(token):
    """Validate token format."""
    if not isinstance(token, str):
        raise vol.Invalid("Invalid token")
    token = token.strip()
    if not 16 <= len(token) <= 64:
        raise vol.Invalid("Invalid token length")
    if not token.isalnum():
        raise vol.Invalid("Invalid token characters")
    return token

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required("model", default=DEFAULT_MODEL): str,
        vol.Required(CONF_TOKEN, default="8SptZ2l2xnQlb8bSdT8mwA"): str,
    }
)

@config_entries.HANDLERS.register(DOMAIN)
class LifeSmartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LifeSmart Local."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    def __init__(self):
        """Initialize the config flow."""
        self._errors = {}

    # 注意：這裡已經移除了 async_get_options_flow，所以介面上的齒輪會消失

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                try:
                    user_input[CONF_HOST] = validate_host(user_input[CONF_HOST])
                except vol.Invalid:
                    errors["base"] = "invalid_host"
                    raise

                model = user_input.get("model", "")
                if not isinstance(model, str) or not 1 <= len(model) <= 50:
                    errors["base"] = "invalid_model"
                    raise vol.Invalid("Invalid model")

                try:
                    user_input[CONF_TOKEN] = validate_token(user_input[CONF_TOKEN])
                except vol.Invalid:
                    errors["base"] = "invalid_token"
                    raise

                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()

                api = LifeSmartAPI(
                    host=user_input[CONF_HOST],
                    model=user_input["model"],
                    token=user_input[CONF_TOKEN],
                    timeout=10,
                    local_port=0
                )
                
                # Test the connection
                try:
                    await api.async_start()
                    devices = await api.discover_devices()
                finally:
                    await api.async_stop()

                if devices:
                    user_input["local_port"] = api.local_port
                    return self.async_create_entry(
                        title="LifeSmart Hub",
                        data=user_input
                    )
                else:
                    errors["base"] = "no_devices"
                    
            except vol.Invalid:
                if "base" not in errors:
                    errors["base"] = "invalid_config"
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors
        )

    async def async_step_reconfigure(self, user_input=None):
        """Handle the reconfiguration step (點擊三個點 -> 重新設定)."""
        errors = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None:
            try:
                user_input[CONF_HOST] = validate_host(user_input[CONF_HOST])
                user_input[CONF_TOKEN] = validate_token(user_input[CONF_TOKEN])

                api = LifeSmartAPI(
                    host=user_input[CONF_HOST],
                    model=user_input.get("model", DEFAULT_MODEL),
                    token=user_input[CONF_TOKEN],
                    timeout=10,
                    local_port=0
                )
                
                try:
                    await api.async_start()
                    devices = await api.discover_devices()
                finally:
                    await api.async_stop()

                if devices:
                    user_input["local_port"] = api.local_port
                    return self.async_update_reload_and_abort(
                        entry,
                        data={**entry.data, **user_input},
                    )
                else:
                    errors["base"] = "no_devices"

            except vol.Invalid:
                errors["base"] = "invalid_config"
            except Exception:
                errors["base"] = "cannot_connect"

        # 預先填入舊有的設定值
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST)): str,
                vol.Required("model", default=entry.data.get("model", DEFAULT_MODEL)): str,
                vol.Required(CONF_TOKEN, default=entry.data.get(CONF_TOKEN)): str,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors
        )

    async def async_step_import(self, user_input=None):
        """Handle import from configuration.yaml."""
        return await self.async_step_user(user_input)
