"""
config.py
Application-wide configuration: persisted user settings, logging setup,
color palette, and user-facing error message mapping.
"""

import json
import logging
from pathlib import Path

# ----------------------------------------------------------------- Paths
CONFIG_FILE = Path.home() / ".yt_downloader_config.json"
LOG_FILE = Path.home() / ".yt_downloader.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger("yt_downloader")

# --------------------------------------------------------------- Colors
COLOR_ERROR = "#E5484D"
COLOR_OK = "#30A46C"
COLOR_WORK = "#F5A524"
COLOR_INFO = "#3B8ED0"

APP_TITLE = "YouTube Downloader PRO"
APP_VERSION = "2.0.0"

# -------------------------------------------------------- Error messages
# User-facing, friendly explanations for the most common failure cases.
ERROR_MESSAGES = {
    "RegexMatchError": "الرابط غير صالح.",
    "VideoUnavailable": "الفيديو غير متاح.",
    "VideoPrivate": "هذا الفيديو خاص.",
    "AgeRestrictedError": "الفيديو مقيّد بالعمر.",
    "MembersOnly": "الفيديو للأعضاء فقط.",
    "LiveStreamError": "لا يمكن تحميل بث مباشر.",
    "URLError": "مشكلة في الاتصال بالإنترنت.",
    "ConnectionError": "مشكلة في الاتصال بالإنترنت.",
    "TimeoutError": "انتهت مهلة الاتصال.",
    "gaierror": "مشكلة في الاتصال بالإنترنت.",
    "DownloadCancelled": "تم إلغاء التحميل.",
}
DEFAULT_ERROR_MESSAGE = (
    "حدث خطأ غير متوقع. قد يكون سبب ذلك تحديثاً في يوتيوب نفسه — "
    "جرّب تحديث المكتبة عبر: pip install -U pytubefix"
)

# --------------------------------------------------------- Default settings
DEFAULT_SETTINGS = {
    "appearance": "System",
    "mode": "video",
    "quality": "Highest",
    "folder": str(Path.home() / "Downloads"),
    "disclaimer_accepted": False,
}


def load_config() -> dict:
    """Loads persisted settings, filling in any missing keys with defaults."""
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    merged = DEFAULT_SETTINGS.copy()
    merged.update(data)
    return merged


def save_config(data: dict) -> None:
    try:
        CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        logger.error("Failed to save config: %s", e)
