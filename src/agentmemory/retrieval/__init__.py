"""Retrieval helpers that sit on top of ``cmd_search``.

Only :mod:`agentmemory.retrieval.answerability` lives here today. The other
optional imports in ``cmd_search`` (``query_planner``, ``late_reranker``,
``diagnostics``) are still absent and keep falling back silently.
"""
