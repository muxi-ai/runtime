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
    RECALL_QUESTION,
)
"""Tuple of all built-in intents. The classifier registers these eagerly
at warmup so the first real classify call doesn't pay prototype-embed
latency."""
