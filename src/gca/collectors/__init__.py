from .appstore import AppStoreCollector
from .base import Collector
from .itch import ItchCollector
from .steam import SteamCollector

__all__ = ["Collector", "SteamCollector", "AppStoreCollector", "ItchCollector"]
