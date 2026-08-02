import os
import threading
from collections import deque
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()

class GroqKeyManager:
    """Thread-safe round-robin API key manager for Groq."""
    
    def __init__(self, keys: Optional[List[str]] = None):
        if keys is None:
            raw_keys = os.getenv("GROQ_API_KEYS", "")
            keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
            
        if not keys:
            raise ValueError("No GROQ_API_KEYS found in environment.")
            
        self._keys = deque(keys)
        self._lock = threading.Lock()
        
    def get_key(self) -> str:
        """Get the current API key at the front of the queue."""
        with self._lock:
            return self._keys[0]
            
    def rotate_key(self, failed_key: str):
        """Move the failed key to the back of the queue if it is currently at the front."""
        with self._lock:
            # Only rotate if the failed key is still at the front
            # This prevents multiple threads from rotating the same key multiple times
            if self._keys and self._keys[0] == failed_key:
                current = self._keys.popleft()
                self._keys.append(current)

# Global instance
_key_manager = None

def get_key_manager() -> GroqKeyManager:
    global _key_manager
    if _key_manager is None:
        _key_manager = GroqKeyManager()
    return _key_manager

def get_groq_api_key() -> str:
    return get_key_manager().get_key()
