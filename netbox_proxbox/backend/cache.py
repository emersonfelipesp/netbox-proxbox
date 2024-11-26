from typing import Any

class Cache:
    def __init__(self):
        self.cache: dict = {}
    
    def get(self, key: str):
        result = self.cache.get(key, {})
        return result
        
    def set(self, key: str, value: Any):
        self.cache[key] = value
    
    def delete(self, key: str):
        try:
            self.cache.pop(key)
        except KeyError:
            pass

cache = Cache()
    
    
    

        