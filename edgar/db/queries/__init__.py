"""
db.queries - Database query functions organized by domain

Usage:
    from edgar import db

    # Entities
    db.queries.entities.get(conn, cik=cik)
    db.queries.entities.select(conn, tickers=None)

    # Concepts
    db.queries.concepts.select_by_entity(conn, cik)
    db.queries.concepts.select_by_role(conn, access_no, role)
    db.queries.concepts.frequency(conn, cik, roles)

    # Facts
    db.queries.facts.insert(conn, facts_list)
    db.queries.facts.select_past_modes(conn, cik, fiscal_year, cid, dimensions)

    # Filings
    db.queries.filings.insert_dei(conn, dei_data)
"""

# Import submodules
from . import entities
from . import concepts
from . import filings
from . import roles
from . import role_patterns
from . import concept_patterns
from . import groups
from . import facts

__all__ = [
    'entities',
    'concepts',
    'filings',
    'roles',
    'role_patterns',
    'concept_patterns',
    'groups',
    'facts',
]
