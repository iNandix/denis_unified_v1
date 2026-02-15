import time
import socket
import threading
import os

class InternetHealth:
    def __init__(self, ttl_s=30):
        self.status = os.getenv("DENIS_INTERNET_STATUS", "UNKNOWN")
        self.last_check_ts = 0
        self.ttl = ttl_s
        self._lock = threading.Lock()

    def check(self) -> str:
        forced = os.getenv("DENIS_INTERNET_STATUS")
        if forced:
            return forced
        
        now = time.time()
        if now - self.last_check_ts < self.ttl:
            return self.status
        
        with self._lock:
            try:
                socket.gethostbyname("8.8.8.8")  # DNS ligero
                self.status = "OK"
            except OSError:
                self.status = "DOWN"
            self.last_check_ts = now
        return self.status

_internet_health = InternetHealth()
def get_internet_health() -> InternetHealth:
    return _internet_health
