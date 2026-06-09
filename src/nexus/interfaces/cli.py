"""
cli.py — Command-line interface parser for the Nexus Engine.
Parses arguments for text queries and applies metadata filters for the Vault Reader agent.
"""
import sys
import argparse

def parse_cli_args(args_list):
    """
    Parses CLI arguments for the Nexus Engine.
    Returns (query: str, filters: dict)
    """
    parser = argparse.ArgumentParser(
        description="Nexus Engine",
        usage='python engine/main.py "your question" [--domain DOMAIN] [--tag TAG] [--type TYPE]',
    )
    parser.add_argument("query", nargs="+", help="Your question for the brain")
    parser.add_argument("--domain", type=str, default=None,
                        help="Filter by domain (health, career, tech, personal, meta, projects, learning)")
    parser.add_argument("--tag", type=str, default=None,
                        help="Filter by tag substring (e.g. 'medical', 'ai', 'finance')")
    parser.add_argument("--type", type=str, default=None,
                        help="Filter by note type (e.g. 'journal', 'overview', 'workshop')")

    args = parser.parse_args(args_list)
    query = " ".join(args.query)

    filters = {}
    if args.domain:
        filters["domain"] = args.domain
    if args.tag:
        filters["tag"] = args.tag
    if args.type:
        filters["type"] = args.type

    return query, filters if filters else None
