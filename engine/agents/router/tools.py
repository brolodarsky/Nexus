"""
tools.py — Tools for the Router Agent.
"""
from langchain_core.tools import tool

@tool
def fetch_emails(query: str) -> str:
    """If the user asks to check their email, read a recent email, or mentions an email, use this tool to retrieve the email data."""
    from agents.email.api import fetch_emails as _fetch
    return _fetch(query)
