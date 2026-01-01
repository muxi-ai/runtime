Compare these two scheduling task descriptions and determine if they represent fundamentally different tasks:

Task 1: {old_prompt}
Task 2: {new_prompt}

Return JSON: {{"different_task": true/false, "reason": "brief explanation"}}

Consider them DIFFERENT tasks if:
- The main action changes (e.g., "send email" vs "backup files")
- The target/object changes significantly (e.g., "email boss" vs "email team")
- The core purpose changes (e.g., "notify" vs "analyze")

Consider them the SAME task if:
- Only minor wording changes
- Same intent expressed in different languages
- Grammatical variations or synonyms
- Added/removed articles or small words

Be language-agnostic - same task in different languages should be considered the same.