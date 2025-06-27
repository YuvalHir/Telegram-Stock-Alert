import time

class MarketDataCache:
    def __init__(self, expiration_hours=3):
        """
        Initializes the MarketDataCache with an expiration time in hours.
        """
        self.cache = {}
        self.expiration_seconds = expiration_hours * 3600 # Convert hours to seconds

    def set(self, key, value):
        """
        Sets a value in the cache with the current timestamp.
        """
        self.cache[key] = {
            "value": value,
            "timestamp": time.time()
        }

    def get(self, key):
        """
        Retrieves a value from the cache if it's not expired.
        Returns the cached value or None if expired or not found.
        """
        if key in self.cache:
            cached_item = self.cache[key]
            if (time.time() - cached_item["timestamp"]) < self.expiration_seconds:
                return cached_item["value"]
            else:
                # Cache expired, remove it
                del self.cache[key]
        return None

# Create a global instance of the cache
market_cache = MarketDataCache(expiration_hours=3)