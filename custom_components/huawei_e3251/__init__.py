import logging
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    EVENT_NEW_SMS,
    CONF_HOST,
    DEFAULT_HOST,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)
from .coordinator import E3251Coordinator
from .modem import E3251Modem

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SELECT,
    Platform.BUTTON,
]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialize Huawei E3251 Module via Config Entry."""
    host = entry.data.get(CONF_HOST, DEFAULT_HOST)
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    # 1. Create modem instance with shared aiohttp session
    session = async_get_clientsession(hass)
    modem = E3251Modem(session, host=host)

    # 2. Create coordinator instance
    coordinator = E3251Coordinator(hass, modem, scan_interval, _LOGGER, entry.entry_id)

    # Load stored SMS history from SQLite database to RAM
    await coordinator._async_setup()

    # Fetch initial data from modem
    await coordinator.async_config_entry_first_refresh()

    # 3. Setup listeners (SMS Event) and storage
    _async_add_listeners(hass, coordinator)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # 4. Servisleri Platform yüklemesinden ÖNCE kaydet
    register_services(hass)

    # 5. Load platforms (Sensor, Select, Button)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload integration entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Reload integration entry."""
    await hass.config_entries.async_reload(config_entry.entry_id)


def _get_coordinator(hass: HomeAssistant) -> E3251Coordinator | None:
    """Helper to fetch the active coordinator instance from hass.data."""
    domain_data = hass.data.get(DOMAIN, {})
    if not domain_data:
        return None
    return next(iter(domain_data.values()), None)


def register_services(hass: HomeAssistant) -> None:
    """Register integration services globally."""

    if hass.services.has_service(DOMAIN, "send_sms"):
        return

    async def send_sms_service(service: ServiceCall) -> None:
        coord = _get_coordinator(hass)
        if not coord:
            _LOGGER.error("E3251: Active integration entry or coordinator not found!")
            return

        target_raw = service.data.get("target") or service.data.get("number")
        message = service.data.get("message") or service.data.get("text")

        targets: list[str] = []

        # 1. Process incoming phone numbers
        if target_raw:
            if isinstance(target_raw, str):
                targets = [n.strip() for n in target_raw.split(",") if n.strip()]
            elif isinstance(target_raw, list):
                for item in target_raw:
                    if isinstance(item, str):
                        targets.extend([n.strip() for n in item.split(",") if n.strip()])

        # 2. If target is empty, read Helper
        if not targets:
            helper_state = hass.states.get("input_text.sms_bildirim_listesi")
            if helper_state:
                raw_val = helper_state.state
                if raw_val in ("unknown", "unavailable", None, ""):
                    raw_val = helper_state.attributes.get("pattern", "")

                if raw_val and raw_val not in ("unknown", "unavailable"):
                    targets = [n.strip() for n in raw_val.split(",") if n.strip()]

        if not targets or not message:
            _LOGGER.error("E3251: Missing SMS parameters! Targets: %s, Message: %s", targets, message)
            return

        # Async send SMS via modem class
        await coord.modem.async_send_sms(targets, message)

    hass.services.async_register(DOMAIN, "send_sms", send_sms_service)

    async def delete_sms_service(service: ServiceCall) -> None:
        coord = _get_coordinator(hass)
        if not coord:
            _LOGGER.error("E3251: Active integration entry or coordinator not found!")
            return

        sms_id = service.data.get("id")
        sender = service.data.get("sender")
        timestamp = service.data.get("timestamp")

        # 1. Priority: Delete from SQLite database using ID
        if sms_id is not None:
            await coord.async_delete_sms_by_id(int(sms_id))
            return

        # 2. Fallback: Delete using Sender and Timestamp
        if sender and timestamp:
            await coord.async_delete_sms(sender, timestamp)
            return

        _LOGGER.error("E3251: Missing parameters for SMS deletion!")

    hass.services.async_register(DOMAIN, "delete_sms", delete_sms_service)


def _async_add_listeners(hass: HomeAssistant, coord: E3251Coordinator) -> None:
    """Listener triggering event upon new SMS arrival."""
    coord.async_add_listener(
        lambda: _fire_sms_event(hass, coord)
    )


def _fire_sms_event(hass: HomeAssistant, coord: E3251Coordinator) -> None:
    """Fires event to HA Event Bus for each new incoming SMS."""
    for sms in coord.new_sms:
        hass.bus.fire(
            EVENT_NEW_SMS,
            {
                "id": sms.get("id"),
                "sender": sms.get("sender"),
                "content": sms.get("body"),
                "received_at": sms.get("timestamp"),
            },
        )
    coord.new_sms = []
