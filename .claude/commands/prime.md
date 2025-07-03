# Prime the context

1. Read README.md, the files in context/*.md (not recursively), THEN run git ls-files and eza --git-ignore --tree to understand the context of the project.

2. Read the formation spec
   - [MUXI Formation Spec](schemas/formation/README.md)
   - [MUXI Formation directory](schemas/formation/)

3. Read the test plan MUXI_Runtime_Comprehensive_Test_Plan.md, and the test learnings MUXI_Runtime_Testing_Guide.md
4. Understand how I want to run tests (below)


# Run tests one by one

Run **each test one at a time**, in order. For every test, do the following steps **before starting the next**:

1. **Print** to stdout a clear message describing **what the test is supposed to check**.
2. **Print** the **full prompt** that will be sent to `overlord.chat`.
3. **Print** every **observability event** that occurs so the request can be fully traced.
4. **Print** the **raw response** returned from `overlord.chat`.
5. **Print** a short **summary** of the result.

---

## Example output
```
I am testing [description of the test]

Prompt sent to overlord.chat:
[prompt contents]

observability event1
observability event2
...

overlord.chat response:
{
  "response": "..."
}

summary:
[your summary here]
```
---

**Important:** After each test, stop and present the results to me.
**Do not continue** to the next test until I confirm I’m satisfied.

After each test, run the following command on the terminal:

```
say "I'm done"
```
