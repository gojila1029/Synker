"""Tests for analysis handler queued source filtering.

These tests verify that the analysis handler correctly filters sources
by status='queued' in its SQL query (AC-001, AC-008, AC-002).
"""
import re


def test_analysis_handler_sql_includes_status_queued_filter():
    """Test that the SQL query in handlers.py line 599 includes AND status='queued'.

    This test covers AC-001:
    - The SELECT query for sources includes AND status='queued'
    - Only queued sources are fetched and processed
    """
    # Read the handlers.py file and verify the SQL includes the filter
    with open("app/worker/handlers.py") as f:
        content = f.read()

    # Find the analysis handler function
    pattern = r"async def _analysis_handler.*?FROM sources WHERE user_id=\$1[^)]*\)"
    match = re.search(pattern, content, re.DOTALL)

    assert match is not None, "Could not find _analysis_handler source SELECT query"

    query_section = match.group(0)

    # Verify AND status='queued' is present
    assert "AND status='queued'" in query_section, (
        f"Expected SQL to contain AND status='queued', but got: {query_section}"
    )


def test_note_gen_insert_includes_source_id_column():
    """Test that the INSERT INTO jobs statement includes source_id.

    This test covers AC-003 and AC-007:
    - The INSERT statement includes source_id column
    - The INSERT uses SELECT to fetch source_id from candidates
    """
    # Read the candidates.py file and verify the INSERT includes source_id
    with open("app/api/routes/candidates.py") as f:
        content = f.read()

    # Find the approve endpoint function
    pattern = r"INSERT INTO jobs.*?FROM candidates WHERE id=\$2"
    match = re.search(pattern, content, re.DOTALL)

    assert match is not None, "Could not find INSERT INTO jobs statement"

    insert_section = match.group(0)

    # Verify source_id is in the column list
    assert "source_id" in insert_section, (
        f"Expected INSERT to include source_id column, but got: {insert_section}"
    )

    # Verify source_id is being selected
    assert "SELECT" in insert_section and "source_id" in insert_section, (
        f"Expected INSERT...SELECT with source_id, but got: {insert_section}"
    )
