from collections import defaultdict
from datetime import datetime, timedelta

flood = defaultdict(list)

def check_flood(user_id: int, limit: int = 4, seconds: int = 60) -> bool:
    now = datetime.now()
    times = [t for t in flood[user_id] if now - t < timedelta(seconds=seconds)]
    flood[user_id] = times
    if len(times) >= limit:
        return True
    flood[user_id].append(now)
    return False
