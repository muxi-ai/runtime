# Example: Precise Arithmetic

**Question:** "If I invest $12,500 at 4.35% compounded monthly, what is it worth after 7 years?"

**File to write (`main.py`):**

```python
principal = 12500.0
rate = 0.0435
n = 12
years = 7

amount = principal * (1 + rate / n) ** (n * years)
print(f"{amount:.2f}")
```

**Invocation:**

```
run_skill(
    skill_name="compute",
    command="python3 scripts/run_python.py main.py",
    input_files={"main.py": "<the code above>"},
)
```

**Expected stdout:**

```
16940.01
```

**Using the result:** Report the value in the answer: "After 7 years the
investment would be worth $16,940.01." Do not show the code.
