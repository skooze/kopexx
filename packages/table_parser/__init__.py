"""Parse tables embedded in footnote source blocks.

OWNS: row and column structure, header hierarchy, cell provenance, exact numeric text.

DOES NOT OWN: financial interpretation. No cell is classified, converted, or computed here.
"""

from .parser import (
    PARSED,
    PARSED_WITH_WARNINGS,
    PARSER_VERSION,
    UNSUPPORTED,
    Cell,
    ParsedTable,
    cell_text,
    parse_table,
    parse_tables,
)

__all__ = [
    "PARSED",
    "PARSED_WITH_WARNINGS",
    "PARSER_VERSION",
    "UNSUPPORTED",
    "Cell",
    "ParsedTable",
    "cell_text",
    "parse_table",
    "parse_tables",
]
