import redis
import json
import os

# --- Redis Connection ---
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True  # strings not bytes
)

# --- Base Utility Functions ---

def set_cache(key: str, value: dict | list | str, ttl: int = None):
    """Set a key in Redis with optional TTL (seconds)."""
    try:
        serialized = json.dumps(value)
        if ttl:
            redis_client.setex(key, ttl, serialized)
        else:
            redis_client.set(key, serialized)
    except Exception as e:
        print(f"[Redis] Error setting cache for {key}: {e}")

def get_cache(key: str):
    """Get a key from Redis and deserialize it."""
    try:
        cached = redis_client.get(key)
        if cached:
            return json.loads(cached)
        return None
    except Exception as e:
        print(f"[Redis] Error getting cache for {key}: {e}")
        return None

def delete_cache(key: str):
    """Delete a cache key."""
    try:
        redis_client.delete(key)
    except Exception as e:
        print(f"[Redis] Error deleting cache for {key}: {e}")

# --- Inbox Caching ---

def cache_inbox(lead_id: str, messages: list, ttl: int = 300):
    key = f"inbox:{lead_id}"
    set_cache(key, messages, ttl)

def get_cached_inbox(lead_id: str):
    return get_cache(f"inbox:{lead_id}")

def invalidate_inbox(lead_id: str):
    delete_cache(f"inbox:{lead_id}")

# --- Contact Caching ---

def cache_contact(contact_id: str, data: dict, ttl: int = 1800):
    key = f"contact:{contact_id}"
    set_cache(key, data, ttl)

def get_cached_contact(contact_id: str):
    return get_cache(f"contact:{contact_id}")

# --- Campaign Caching ---

def cache_campaigns(data: list, ttl: int = 21600):  # 6 hours
    set_cache("campaigns:list", data, ttl)

def get_cached_campaigns():
    return get_cache("campaigns:list")

# --- Email Template Caching ---

def cache_email_template(template_id: str, data: dict, ttl: int = 86400):  # 24 hours
    key = f"template:email:{template_id}"
    set_cache(key, data, ttl)

def get_cached_email_template(template_id: str):
    return get_cache(f"template:email:{template_id}")

# --- GHL Auth Token Caching ---

def cache_ghl_token(token: str, ttl: int = 900):  # 15 minutes
    set_cache("ghl:access_token", token, ttl)

def get_cached_ghl_token():
    return get_cache("ghl:access_token")