"""Vault intelligence: structured retrieval over Obsidian entity graph."""

from .parser import ParsedNote, parse_note
from .corpus import VaultCorpus

__all__ = ["ParsedNote", "parse_note", "VaultCorpus"]
