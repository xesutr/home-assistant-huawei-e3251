"""Huawei E3251 HiLink SMS Bileşeni Sabitleri."""

DOMAIN = "huawei_e3251"
DEFAULT_NAME = "Huawei E3251 Modem"
DEFAULT_HOST = "10.20.30.50"

# Config Flow ve Ayar Sabitleri
CONF_HOST = "host"
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 20

# Event Sabitleri
EVENT_NEW_SMS = "huawei_e3251_new_sms"

# API Endpoint'leri
ENDPOINT_STATUS = "/api/monitoring/status"
ENDPOINT_SMS_COUNT = "/api/sms/sms-count"
ENDPOINT_SMS_LIST = "/api/sms/sms-list"
ENDPOINT_SEND_SMS = "/api/sms/send-sms"
ENDPOINT_DELETE_SMS = "/api/sms/delete-sms"

# Zorunlu HTTP Başlıkları (Header)
HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"http://{DEFAULT_HOST}/html/smsinbox.html",
    "Origin": f"http://{DEFAULT_HOST}",
}
