"""Social media provider adapters (FR-03).

The ingestion interface is deliberately replaceable: a real provider (e.g. a
licensed social media search API) can be added by implementing
``SocialProvider`` without touching the rest of the system. Only lawful,
authorised, read-only collection of public text is supported — the
application does not scrape protected sources or bypass provider controls.
"""
