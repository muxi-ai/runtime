# Example: Regex Parsing

**Question:** "How many unique error codes appear in this log excerpt, and which is most frequent?" (log text supplied in the conversation)

**File to write (`main.py`):**

```python
import json
import re
from collections import Counter

log = """\
2026-05-01 12:00:01 ERR-4102 timeout on upstream
2026-05-01 12:00:04 ERR-2201 invalid payload
2026-05-01 12:00:09 ERR-4102 timeout on upstream
2026-05-01 12:01:13 ERR-7300 quota exceeded
2026-05-01 12:02:44 ERR-4102 timeout on upstream
"""

codes = re.findall(r"ERR-\d{4}", log)
counts = Counter(codes)
top_code, top_count = counts.most_common(1)[0]

print(json.dumps({
    "unique_codes": len(counts),
    "most_frequent": top_code,
    "occurrences": top_count,
}))
```

**Expected stdout:**

```
{"unique_codes": 3, "most_frequent": "ERR-4102", "occurrences": 3}
```

**Using the result:** "There are 3 unique error codes; ERR-4102 is the most
frequent with 3 occurrences." Embed the data to parse directly in the file
as a literal - the script has no access to the conversation.
