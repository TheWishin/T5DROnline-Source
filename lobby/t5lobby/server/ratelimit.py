"""Token buckets and a small ban list for abuse protection."""
import time


class TokenBucket:
    """`rate` tokens per second, at most `burst` stored. take() -> True if allowed."""
    __slots__ = ("rate", "burst", "tokens", "t")

    def __init__(self, rate, burst, clock=time.monotonic):
        self.rate = float(rate)
        self.burst = float(burst)
        self.tokens = float(burst)
        self.t = clock()

    def take(self, n=1.0, now=None):
        now = time.monotonic() if now is None else now
        self.tokens = min(self.burst, self.tokens + (now - self.t) * self.rate)
        self.t = now
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False


class KeyedBuckets:
    """One TokenBucket per key (IP, account name, ...), forgotten when full again."""

    def __init__(self, rate, burst, max_keys=100000):
        self.rate, self.burst, self.max_keys = rate, burst, max_keys
        self.b = {}

    def take(self, key, n=1.0):
        now = time.monotonic()
        bucket = self.b.get(key)
        if bucket is None:
            if len(self.b) >= self.max_keys:
                self.prune(now)
            bucket = self.b[key] = TokenBucket(self.rate, self.burst)
        return bucket.take(n, now)

    def peek_ok(self, key, n=1.0):
        """Would take() succeed? (does not consume)"""
        bucket = self.b.get(key)
        if bucket is None:
            return True
        now = time.monotonic()
        return min(bucket.burst, bucket.tokens + (now - bucket.t) * bucket.rate) >= n

    def prune(self, now=None):
        now = time.monotonic() if now is None else now
        dead = [k for k, bk in self.b.items() if bk.tokens + (now - bk.t) * bk.rate >= bk.burst]
        for k in dead:
            del self.b[k]


class BanList:
    """Temporary bans by key (IP address)."""

    def __init__(self):
        self.until = {}

    def ban(self, key, seconds):
        self.until[key] = max(self.until.get(key, 0.0), time.monotonic() + seconds)

    def banned(self, key):
        t = self.until.get(key)
        if t is None:
            return False
        if time.monotonic() >= t:
            del self.until[key]
            return False
        return True
