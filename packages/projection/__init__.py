"""The lossless, offset-anchored projection of a preserved filing into one YAML document.

WHY THIS PACKAGE EXISTS, IN ONE MEASUREMENT. Apple's 10-Q is 915,890 characters as SEC published it
and 142,096 characters of words a person reads. Sent intact it costs roughly 254,000 tokens and no
approved candidate can hold it; projected it costs roughly 62,000 and every one of them can, with
between 66,000 and 200,000 tokens of context to spare. The filing was never too big. The markup was.

WHAT IT DOES AND DOES NOT DO. It changes SYNTAX and never MEANING: prose blocks at their source
offsets, tables as the grids their own markup describes, images by identity. No title, no section,
no type, no classification, no judgement about importance. The original artifact is untouched,
preserved and authoritative, and every citation a model makes is proved against SEC's bytes rather
than against this document.

IT REQUIRED AN EXPLICIT RULE CHANGE AND DID NOT GET ONE QUIETLY. `rules.md` section 21 rule 7 listed
visible-content projection as an unapproved research option through two phases, and the content
boundary said in as many words "never rewrite an original artifact into YAML". Both were amended by
ADR-0022, on the evidence above, and the amendment is narrow: the projection is lossless over
everything human-readable, it is checked rather than asserted, and it carries the offsets that make
it reversible.
"""

from .document import SCHEMA_VERSION, project, projection_note
from .errors import ProjectionError, ProjectionIncompleteError

__all__ = [
    "SCHEMA_VERSION",
    "ProjectionError",
    "ProjectionIncompleteError",
    "project",
    "projection_note",
]
