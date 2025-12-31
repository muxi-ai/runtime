Determine if we need more clarification.

Original request: {original_request}
Information collected so far: {collected_info}
Mode: {mode}

Do we have enough to proceed? If not, what should we ask next?

Question Style: {style}
Style Guidelines:
- conversational: Natural, friendly, like a helpful colleague
- technical: Precise, specific, professional
- brief: Very concise, minimal words

Return JSON:
{{
    "needs_more": boolean,
    "question": "next question in the specified style or null"
}}

Be practical - if we have enough to make progress, don't over-clarify.