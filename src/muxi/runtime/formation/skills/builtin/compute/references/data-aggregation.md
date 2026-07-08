# Example: Data Aggregation

**Question:** "Given these sales rows, what is the average order value per region?" (rows supplied in the conversation)

**File to write (`main.py`):**

```python
import json
import pandas as pd

rows = [
    {"region": "north", "amount": 120.50},
    {"region": "south", "amount": 89.99},
    {"region": "north", "amount": 240.00},
    {"region": "east", "amount": 55.25},
    {"region": "south", "amount": 310.10},
]

df = pd.DataFrame(rows)
avg = df.groupby("region")["amount"].mean().round(2)
print(json.dumps(avg.to_dict()))
```

**Expected stdout:**

```
{"east": 55.25, "north": 180.25, "south": 200.04}
```

**Using the result:** "Average order value: North $180.25, South $200.04,
East $55.25." For plain statistics without grouping, the `statistics`
module is enough - reach for pandas only when rows and grouping are involved.
