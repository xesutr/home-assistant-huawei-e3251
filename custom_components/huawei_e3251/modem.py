import logging
import aiohttp
from datetime import datetime
import xml.etree.ElementTree as ET

from .const import (
    DEFAULT_HOST,
    ENDPOINT_STATUS,
    ENDPOINT_SMS_COUNT,
    ENDPOINT_SMS_LIST,
    ENDPOINT_SEND_SMS,
    ENDPOINT_DELETE_SMS,
    HEADERS,
)

_LOGGER = logging.getLogger(__name__)


class E3251Modem:
    """HTTP API Driver for Huawei E3251 HiLink GSM Modem."""

    def __init__(self, session: aiohttp.ClientSession, host: str = DEFAULT_HOST) -> None:
        self.session = session
        self.host = host
        self.base_url = f"http://{host}"

    async def async_send_sms(self, targets: list[str], message: str) -> bool:
        """Send SMS messages to multiple recipients via HiLink HTTP API."""
        url = f"{self.base_url}{ENDPOINT_SEND_SMS}"
        all_success = True

        for number in targets:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            msg_len = len(message)

            payload = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                f"<request>"
                f"<Index>-1</Index>"
                f"<Phones><Phone>{number}</Phone></Phones>"
                f"<Sca></Sca>"
                f"<Content>{message}</Content>"
                f"<Length>{msg_len}</Length>"
                f"<Reserved>1</Reserved>"
                f"<Date>{now_str}</Date>"
                f"</request>"
            )

            try:
                async with self.session.post(url, data=payload, headers=HEADERS, timeout=10) as response:
                    if response.status == 200:
                        text = await response.text()
                        if "<response>OK</response>" in text:
                            _LOGGER.info("E3251: SMS sent successfully to %s", number)
                        else:
                            _LOGGER.error("E3251: Modem error response for %s: %s", number, text)
                            all_success = False
                    else:
                        _LOGGER.error("E3251: HTTP %s error sending SMS to %s", response.status, number)
                        all_success = False
            except Exception as num_err:
                _LOGGER.error("E3251: Exception sending SMS to %s: %s", number, num_err)
                all_success = False

        return all_success

    async def async_read_unread_sms(self) -> list[dict]:
        """Read unread SMS messages using HiLink HTTP API."""
        messages = []

        # 1. Light check via sms-count endpoint
        count_url = f"{self.base_url}{ENDPOINT_SMS_COUNT}"
        try:
            async with self.session.get(count_url, timeout=5) as resp:
                if resp.status == 200:
                    count_text = await resp.text()
                    root_count = ET.fromstring(count_text)
                    local_unread = int(root_count.findtext("LocalUnread", "0"))
                    sim_unread = int(root_count.findtext("SimUnread", "0"))

                    if local_unread == 0 and sim_unread == 0:
                        return []
        except Exception as err:
            _LOGGER.error("E3251: Could not check SMS count: %s", err)
            return []

        # 2. If unread SMS exists, fetch message list
        list_url = f"{self.base_url}{ENDPOINT_SMS_LIST}"
        payload = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<request>"
            "<PageIndex>1</PageIndex>"
            "<ReadCount>20</ReadCount>"
            "<BoxType>1</BoxType>"
            "<SortType>0</SortType>"
            "<Ascending>0</Ascending>"
            "<UnreadPreferred>0</UnreadPreferred>"
            "</request>"
        )

        try:
            async with self.session.post(list_url, data=payload, headers=HEADERS, timeout=10) as response:
                if response.status == 200:
                    text = await response.text()
                    root = ET.fromstring(text)
                    msgs_node = root.find("Messages")

                    if msgs_node is not None:
                        for msg in msgs_node.findall("Message"):
                            index = msg.findtext("Index")
                            phone = msg.findtext("Phone", "Unknown")
                            content = msg.findtext("Content", "")
                            date = msg.findtext("Date", "")

                            messages.append({
                                "index": index,
                                "sender": phone,
                                "body": content,
                                "timestamp": date,
                                "ref_id": None,
                                "total_parts": 1,
                                "part_num": 1,
                            })
        except Exception as e:
            _LOGGER.error("E3251: Error reading SMS list: %s", e)

        return messages

    async def async_delete_all_read_sms(self, processed_messages: list[dict]) -> bool:
        """Deletes processed SMS messages from modem memory by Index."""
        url = f"{self.base_url}{ENDPOINT_DELETE_SMS}"
        all_deleted = True

        for msg in processed_messages:
            idx = msg.get("index")
            if not idx:
                continue

            payload = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                f"<request><Index>{idx}</Index></request>"
            )

            try:
                async with self.session.post(url, data=payload, headers=HEADERS, timeout=5) as response:
                    if response.status == 200:
                        text = await response.text()
                        if "<response>OK</response>" in text:
                            _LOGGER.debug("E3251: Modem SMS index %s deleted successfully.", idx)
                        else:
                            _LOGGER.warning("E3251: Failed to delete SMS index %s: %s", idx, text)
                            all_deleted = False
            except Exception as e:
                _LOGGER.error("E3251: Exception deleting SMS index %s: %s", idx, e)
                all_deleted = False

        return all_deleted

    async def async_get_signal_strength(self) -> int:
        """Read signal strength percentage from /api/monitoring/status."""
        url = f"{self.base_url}{ENDPOINT_STATUS}"
        try:
            async with self.session.get(url, headers=HEADERS, timeout=5) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    if "<SignalIcon>" in text:
                        val_str = text.split("<SignalIcon>")[1].split("</SignalIcon>")[0]
                        icon_val = int(val_str)
                        return min(100, max(0, icon_val * 20))
        except Exception as e:
            _LOGGER.error("E3251: Signal status read error: %s", e)
        return 0
