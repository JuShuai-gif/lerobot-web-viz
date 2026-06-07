from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class FrameCacheKey:
    episode_id: int
    frame_id: int
    camera_name: str
    quality: int


class LRUFrameCache:
    def __init__(self, max_items: int) -> None:
        self.max_items = max(1, max_items)
        self._items: OrderedDict[FrameCacheKey, bytes] = OrderedDict()
        self._lock = RLock()

    def get(self, key: FrameCacheKey) -> bytes | None:
        with self._lock:
            value = self._items.get(key)
            if value is None:
                return None
            self._items.move_to_end(key)
            return value

    def put(self, key: FrameCacheKey, value: bytes) -> None:
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)

    def clear_episode(self, episode_id: int) -> None:
        with self._lock:
            for key in list(self._items):
                if key.episode_id == episode_id:
                    self._items.pop(key, None)
