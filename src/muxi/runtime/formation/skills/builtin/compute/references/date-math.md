# Example: Date Math

**Question:** "A meeting starts 2026-03-27 09:30 in New York. What time is that in Tokyo, and how many days away is it from 2026-01-15?"

**File to write (`main.py`):**

```python
import json
from datetime import datetime, date
from zoneinfo import ZoneInfo

start_ny = datetime(2026, 3, 27, 9, 30, tzinfo=ZoneInfo("America/New_York"))
start_tokyo = start_ny.astimezone(ZoneInfo("Asia/Tokyo"))
days_away = (start_ny.date() - date(2026, 1, 15)).days

print(json.dumps({
    "tokyo_time": start_tokyo.isoformat(),
    "days_from_jan_15": days_away,
}))
```

**Expected stdout:**

```
{"tokyo_time": "2026-03-27T22:30:00+09:00", "days_from_jan_15": 71}
```

**Using the result:** "In Tokyo the meeting starts at 22:30 on March 27,
which is 71 days after January 15." Structured results print one JSON
object so each field can be read unambiguously.
