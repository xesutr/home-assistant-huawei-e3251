import logging
import voluptuous as vol
from typing import Any
from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    DEFAULT_HOST,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


async def _test_hilink_connection(hass, host: str) -> bool:
    """Modemin HTTP API'sine ulaşılabildiğini test eden yardımcı fonksiyon."""
    url = f"http://{host}/api/monitoring/status"
    try:
        session = async_get_clientsession(hass)
        async with session.get(url, timeout=5) as response:
            if response.status == 200:
                text = await response.text()
                return "<ConnectionStatus>" in text
    except Exception as e:
        _LOGGER.error("Huawei HiLink Bağlantı Test Hatası (%s): %s", host, e)
        return False
    return False


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Arayüzden entegrasyon ekleme akışı."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """İlk ekleme adımı."""
        errors = {}

        # Tekil cihaz kontrolü
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            host = user_input[CONF_HOST]

            # HTTP bağlantısını test et
            success = await _test_hilink_connection(self.hass, host)

            if success:
                return self.async_create_entry(
                    title=f"Huawei E3251 ({host})", 
                    data=user_input
                )
            else:
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=DEFAULT_HOST): cv.string,
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlowWithConfigEntry):
    """Cihaz Ayarlarını (Yapılandır) menüsünden güncelleme akışı."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors = {}
        data = user_input or self.config_entry.data

        if user_input is not None:
            host = user_input[CONF_HOST]

            success = await _test_hilink_connection(self.hass, host)

            if success:
                self.hass.config_entries.async_update_entry(self.config_entry, data=user_input)
                return self.async_create_entry(title="", data=user_input)
            else:
                errors["base"] = "cannot_connect"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=data.get(CONF_HOST, DEFAULT_HOST)): cv.string,
                vol.Required(CONF_SCAN_INTERVAL, default=data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): int,
            }
        )

        return self.async_show_form(step_id="init", data_schema=data_schema, errors=errors)
