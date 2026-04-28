"""Curated example sentences for each binary pre-planning gate.

Each :class:`IntentSpec` carries two lists of natural-language exemplars:
``positive`` (texts whose correct gate decision is True) and ``negative``
(texts whose correct gate decision is False). At classify time the
:class:`~.local_classifier.LocalClassifier` embeds the query and computes
its cosine similarity against the centroid of each list, returning the
label with the larger similarity.

Prototype sets are intentionally small (10-25 examples each). Larger sets
don't help once the centroid stabilizes, and they slow the one-shot
prototype embedding pass at warmup. We rely on the multilingual e5-small
encoder's strong semantic clustering, not on label-set memorization.

A handful of non-English exemplars are included on every gate. They
exist to keep the centroid honest when a user types in Spanish or
Japanese — not to provide exhaustive multilingual coverage.

Authoring guidelines
--------------------

* Keep examples short (<100 chars). Long contexts dilute the centroid.
* Cover the common phrasings actually seen in production traces, not
  invented edge cases.
* When swapping prompt wording in the corresponding overlord /
  clarification gate, update these exemplars to match.
* Avoid ambiguous examples on either side. "Could you maybe help with
  X?" is borderline — picking a side hurts the centroid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class IntentSpec:
    """Curated positive/negative example sets for one binary gate.

    Attributes
    ----------
    name:
        Stable identifier used as the registration key on the
        classifier. Pick a short snake_case string; downstream call
        sites pass this string verbatim.
    positive:
        Sentences whose correct gate decision is ``True``.
    negative:
        Sentences whose correct gate decision is ``False``.
    description:
        Free-form description of what ``True`` means for this gate.
        Used in tests + diagnostic output. Not embedded.
    """

    name: str
    description: str
    positive: List[str]
    negative: List[str]


ACTIONABILITY = IntentSpec(
    name="actionable",
    description=(
        "True when the message asks the system to DO something — answer a "
        "question, explain a concept, fetch information, take an action, or "
        "produce content. False only for bare social chatter."
    ),
    positive=[
        "What database should I use for this project?",
        "Create a hello world Python script",
        "Tell me about MUXI",
        "Explain how formations work",
        "How does the overlord coordinate agents?",
        "What is the difference between buffer and persistent memory?",
        "Why is my deployment failing?",
        "Summarize this PDF for me",
        "Write a blog post about AI agents",
        "Fix the bug in my login flow",
        "Compare these two documents",
        "Generate a one-page report on quarterly sales",
        "Show me my scheduled jobs",
        "Search the docs for memory configuration",
        "Help me understand vector search",
        "1. core features 2. developers 3. casual use",  # numbered answer to assistant questions
        "que base de datos debo usar?",
        "Explique como funcionan las formaciones",
    ],
    negative=[
        "Hi",
        "Hello",
        "Hey there",
        "Good morning",
        "Good afternoon",
        "Thanks",
        "Thank you so much",
        "Got it",
        "Okay",
        "Cool",
        "Nice, thanks",
        "Sounds good",
        "Awesome",
        "Hola",
        "Gracias",
        "Bonjour",
        "Merci beaucoup",
    ],
)


WORKFLOW_ELIGIBILITY = IntentSpec(
    name="workflow_eligible",
    description=(
        "True when the message warrants treating as a real request that may "
        "trigger workflow / decomposition. Stricter than actionability — "
        "rejects pure information statements that don't ask for anything."
    ),
    positive=[
        "Build me a deployment pipeline for the staging environment",
        "Research the top three vector databases and write up a comparison",
        "Refactor this module to use async I/O",
        "Plan a marketing campaign for the new feature launch",
        "Implement OAuth login with Google",
        "Analyze this dataset and generate insights",
        "Set up monitoring and alerting for the API",
        "Migrate the database from SQLite to PostgreSQL",
        "Write tests for the authentication flow",
        "Investigate the slow query and propose a fix",
        "Crea una API REST para gestionar usuarios",
    ],
    negative=[
        "Hi",
        "Hello",
        "Thanks",
        "Got it",
        "I'm using Python",  # informational statement
        "My budget is around $5000",
        "The deadline is next Friday",
        "I prefer dark mode",
        "Yes",
        "No",
        "Maybe later",
        "Sure",
        "OK",
        "Hola",
        "Gracias",
    ],
)


SIMPLE_QUESTION = IntentSpec(
    name="simple_question",
    description=(
        "True when the message is a simple question answerable in a few "
        "sentences without multi-step work. False when the message requires "
        "research, multiple steps, or building/creating something."
    ),
    positive=[
        "What is the capital of France?",
        "What does FAISS stand for?",
        "How do I install Python on macOS?",
        "What's the difference between a list and a tuple?",
        "Recommend a good book on distributed systems",
        "What's a good name for a startup that makes AI agents?",
        "Why is the sky blue?",
        "When was Python first released?",
        "Who created the C programming language?",
        "What's the best way to learn Rust?",
        "Define recursion in plain English",
        "Cual es la capital de Japon?",
    ],
    negative=[
        "Build a web app with user authentication and a Postgres backend",
        "Research the top five JavaScript frameworks, compare them on bundle size and runtime performance, and pick a winner",
        "Refactor the entire authentication module to use async/await and add comprehensive tests",
        "Migrate the production database to a new schema with zero downtime",
        "Implement, test, deploy, and monitor a new microservice for billing",
        "Build a chatbot that ingests our company documentation and answers customer questions",
        "Plan and execute a multi-region failover for the staging cluster",
        "Crea una aplicacion web completa con autenticacion y base de datos",
    ],
)


CLARIFICATION_CONTEXT_SWITCH = IntentSpec(
    name="clarification_context_switch",
    description=(
        "True when, in the middle of an active clarification flow, the user "
        "responds with something that is clearly off-topic from the original "
        "request — i.e. they want to break out of the clarification and ask "
        "about something else entirely."
    ),
    positive=[
        "Actually, never mind that — what's the weather today?",
        "Forget about the deployment, can you instead help me debug a Python error?",
        "Wait, different question: how do I reset my password?",
        "Hold on, can we talk about something else first?",
        "Switch topics — tell me about your memory architecture",
        "Skip that, I want to know how SOPs work",
        "Olvida eso, mejor cuentame sobre las formaciones",
    ],
    negative=[
        "Yes, use Postgres",  # answering the clarification
        "The staging environment, please",
        "Both options work, you pick",
        "Just the title, nothing else",
        "Yes, that's correct",
        "Make it green",
        "I prefer the second option",
        "Whatever you think is best",
        "Si, esa es la opcion correcta",
    ],
)


CLARIFICATION_STOP_INTENT = IntentSpec(
    name="clarification_stop",
    description=(
        "True when, in the middle of an active clarification flow, the user "
        "wants to stop being asked questions and have the system proceed "
        "with whatever it knows — same topic, just done with clarifying."
    ),
    positive=[
        "Just do it",
        "Stop asking and proceed",
        "Enough questions, go ahead",
        "Never mind the questions, just start",
        "Forget the questions, get started",
        "Skip the questions",
        "Just go ahead with whatever",
        "OK enough, start",
        "Basta de preguntas, hazlo",
    ],
    negative=[
        "Yes, Postgres please",
        "The first option",
        "Both",
        "Make it bigger",
        "I prefer green",
        "The deadline is Friday",
        "Use Python",
        "Yes",
        "No",
        "Si",
    ],
)


CREDENTIAL_CANCELLATION = IntentSpec(
    name="credential_cancellation",
    description=(
        "True when the user, in the middle of a credential-collection "
        "flow, wants to cancel / abort / skip providing the credential. "
        "False for help requests ('how do I get one?') and for actual "
        "credential strings. Multilingual."
    ),
    positive=[
        "cancel",
        "stop",
        "nevermind",
        "never mind",
        "forget it",
        "skip this",
        "skip it for now",
        "abort",
        "I don't want to",
        "no thanks",
        "later",
        "maybe later",
        "not now",
        "pas maintenant",
        "cancelar",
        "olvidalo",
    ],
    negative=[
        "How do I get a token?",
        "Where do I find this?",
        "Can you help me?",
        "I don't know how to get this",
        "What is this for?",
        "Show me how",
        "ghp_abc123def456",  # actual credential string
        "sk-proj-xxxxxxxxxxxx",
        "Bearer eyJhbGciOiJI",
        "my username is alice and password is hunter2",
        "Como obtengo esto?",
        "Comment trouver ca?",
    ],
)


CREDENTIAL_HELP_REQUEST = IntentSpec(
    name="credential_help_request",
    description=(
        "True when the user is asking for help/guidance on obtaining a "
        "credential (where to find it, how to create one). False when "
        "the user is providing an actual credential string or "
        "cancelling. Multilingual."
    ),
    positive=[
        "How do I get a token?",
        "Where do I find my API key?",
        "How do I create one?",
        "Can you help me?",
        "I don't know how to get this",
        "What is this for?",
        "Where can I find this?",
        "I need help getting credentials",
        "Show me how to obtain it",
        "Como obtengo esto?",
        "Donde encuentro mi token?",
        "Comment obtenir ca?",
    ],
    negative=[
        "ghp_abc123def456",
        "sk-proj-xxxxxxxxxxxxxxxxxxxxxxxx",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        "my key is abc123def456",
        "username:password",
        "alice@example.com:hunter2",
        "cancel",
        "nevermind",
        "stop",
        "Here is my token: xyz789",
        "Thanks for helping! API key is 9f8e7d6c5b4a3210",
    ],
)


CREDENTIAL_REQUEST = IntentSpec(
    name="credential_request",
    description=(
        "True when the user is asking to ADD or CONFIGURE a NEW "
        "credential / account. False for ordinary chat requests, "
        "follow-ups, or other tasks unrelated to credential setup."
    ),
    positive=[
        "I need to add a new GitHub account",
        "Configure a new API key",
        "Set up different credentials",
        "Add another account",
        "Connect a new service",
        "I want to add my Notion credentials",
        "Set up a new integration",
        "Register a new account with the system",
        "Anadir nueva cuenta",
        "Add my Slack token",
    ],
    negative=[
        "Tell me about MUXI",
        "What is the capital of France?",
        "Build me a web app",
        "Explain how vector search works",
        "Compare these two documents",
        "Hi",
        "Thanks",
        "Show me my scheduled jobs",
        "Send a message via Slack",
        "Open my GitHub issues",
        "Que es FAISS?",
    ],
)


CLARIFICATION_NEEDED = IntentSpec(
    name="clarification_needed",
    description=(
        "True when the user's request is ambiguous, vague, or missing "
        "essential information that the system cannot reasonably guess. "
        "False when the request is clear enough to act on directly. "
        "Conservative bias: only ambiguity that would change the action "
        "in important ways triggers True."
    ),
    positive=[
        "Help me with the project",
        "Do the thing",
        "Send it",
        "Configure that",
        "Schedule a meeting",
        "Email someone about it",
        "Update the file",
        "Send a notification",
        "Move the task",
        "Make it bigger",
        "Set it up",
        "Run the report",
        "Ayudame con el proyecto",
    ],
    negative=[
        "What is the capital of France?",
        "Tell me about MUXI",
        "Hi",
        "Thanks",
        "Build a one-page PDF about quarterly sales",
        "Schedule a daily standup at 10am every weekday",
        "Send an email to alice@example.com saying the deploy is done",
        "Compare these two PDFs and summarize the differences",
        "Search the docs for buffer memory configuration",
        "What did I tell you about my project?",
        "Explain how formations work",
        "Que es FAISS?",
        "Why is the sky blue?",
        "1. Postgres 2. Redis 3. Both",
        "Yes, use the staging environment",
    ],
)


CLARIFICATION_NEEDS_MORE = IntentSpec(
    name="clarification_needs_more",
    description=(
        "True when the gap between the original request and the "
        "information collected so far is still wide enough that more "
        "questions are warranted. False when collected info is "
        "sufficient to proceed. Embed input is a joint string "
        "concatenating original_request and collected_info — the "
        "centroid encodes 'completeness' as semantic alignment between "
        "the two."
    ),
    positive=[
        "Original: Schedule a meeting\nCollected: {}",
        "Original: Send an email\nCollected: {recipient: alice}",
        "Original: Build a report\nCollected: {topic: sales}",
        "Original: Configure my account\nCollected: {service: github}",
        "Original: Help me set up monitoring\nCollected: {}",
        "Original: Make a presentation\nCollected: {audience: executives}",
        "Original: Plan a trip\nCollected: {destination: Tokyo}",
    ],
    negative=[
        "Original: Schedule a meeting\nCollected: {time: 2pm tomorrow, attendees: [alice, bob], title: Q4 review, duration: 1h}",
        "Original: Send an email\nCollected: {recipient: alice@example.com, subject: deploy done, body: deployed at 3pm, signed off: yes}",
        "Original: Build a report\nCollected: {topic: Q4 sales, length: 1 page, format: PDF, data_source: salesforce, deadline: Friday}",
        "Original: Configure my account\nCollected: {service: github, account_type: enterprise, token: provided, scope: repo+admin, verified: true}",
        "Original: Make a presentation\nCollected: {audience: executives, slides: 10, topic: roadmap, deadline: Monday, theme: corporate-dark, exported: pptx}",
    ],
)


RECALL_QUESTION = IntentSpec(
    name="recall_question",
    description=(
        "True when the user is asking the system to recall something the "
        "user told it earlier in the conversation — their own profile, "
        "preferences, or prior statements. False for general-knowledge "
        "questions or task requests."
    ),
    positive=[
        "What is my name?",
        "What's my favorite database?",
        "What did I tell you about my project?",
        "What is my role at the company?",
        "Remind me what we discussed",
        "What was my preference again?",
        "Summarize what I told you about myself",
        "List back the personal details I shared",
        "What's my email address?",
        "Restate my profession",
        "Cual es mi nombre?",
        "Que te dije sobre mi proyecto?",
    ],
    negative=[
        "What is FastAPI?",
        "How do I install Python?",
        "Can you write a hello world program?",
        "What's the capital of Japan?",
        "Explain vector search",
        "Build me a web app",
        "Why is my code crashing?",
        "Compare these two libraries",
        "Que es FastAPI?",
    ],
)


ALL_INTENTS = (
    ACTIONABILITY,
    WORKFLOW_ELIGIBILITY,
    SIMPLE_QUESTION,
    CLARIFICATION_CONTEXT_SWITCH,
    CLARIFICATION_STOP_INTENT,
    CLARIFICATION_NEEDED,
    CLARIFICATION_NEEDS_MORE,
    CREDENTIAL_CANCELLATION,
    CREDENTIAL_HELP_REQUEST,
    CREDENTIAL_REQUEST,
    RECALL_QUESTION,
)
"""Tuple of all built-in intents. The classifier registers these eagerly
at warmup so the first real classify call doesn't pay prototype-embed
latency."""
