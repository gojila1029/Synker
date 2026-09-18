"""Regression tests for source handling and discovery modes."""
import pytest
from pydantic import ValidationError

from app.schemas.sources import SourceCreate


@pytest.mark.regression
def test_youtube_keyword_requires_keyword_field() -> None:
    """YouTube keyword discovery requires non-empty keyword."""
    with pytest.raises(ValidationError):
        SourceCreate(
            type="youtube",
            discovery_mode="keyword",
            keyword=None,  # Missing keyword
        )


@pytest.mark.regression
def test_youtube_web_keyword_rejected() -> None:
    """YouTube sources cannot use web_keyword mode."""
    with pytest.raises(ValidationError):
        SourceCreate(
            type="youtube",
            discovery_mode="web_keyword",
            keyword="test",
        )


@pytest.mark.regression
def test_web_keyword_discovery_requires_keyword() -> None:
    """Web keyword discovery requires non-empty keyword."""
    with pytest.raises(ValidationError):
        SourceCreate(
            type="web",
            discovery_mode="web_keyword",
            keyword="",  # Empty keyword
        )


@pytest.mark.regression
def test_web_keyword_mode_invalid() -> None:
    """Web sources cannot use keyword mode."""
    with pytest.raises(ValidationError):
        SourceCreate(
            type="web",
            discovery_mode="keyword",
            keyword="test",
        )


@pytest.mark.regression
def test_source_create_valid_youtube_single() -> None:
    """Valid YouTube source with single mode."""
    source = SourceCreate(
        type="youtube",
        title="Test Video",
        url="https://youtube.com/watch?v=abc123",
        discovery_mode="single",
    )
    assert source.type == "youtube"
    assert source.discovery_mode == "single"
    assert source.discovery_limit == 25


@pytest.mark.regression
def test_source_create_valid_youtube_keyword() -> None:
    """Valid YouTube source with keyword discovery."""
    source = SourceCreate(
        type="youtube",
        title="Python Tutorials",
        discovery_mode="keyword",
        keyword="python tutorials",
        discovery_limit=15,
    )
    assert source.keyword == "python tutorials"
    assert source.discovery_limit == 15


@pytest.mark.regression
def test_source_create_valid_web_keyword() -> None:
    """Valid web source with web_keyword discovery."""
    source = SourceCreate(
        type="web",
        discovery_mode="web_keyword",
        keyword="react patterns",
        discovery_limit=5,
    )
    assert source.type == "web"
    assert source.keyword == "react patterns"
    assert source.discovery_limit == 5


@pytest.mark.regression
def test_discovery_limit_bounds_validation() -> None:
    """Discovery limit must be between 1 and 50."""
    # Too low
    with pytest.raises(ValidationError):
        SourceCreate(
            type="web",
            discovery_mode="web_keyword",
            keyword="test",
            discovery_limit=0,
        )

    # Too high
    with pytest.raises(ValidationError):
        SourceCreate(
            type="web",
            discovery_mode="web_keyword",
            keyword="test",
            discovery_limit=51,
        )


@pytest.mark.regression
def test_discovery_limit_valid_bounds() -> None:
    """Discovery limit at boundaries should be valid."""
    # Minimum
    source1 = SourceCreate(
        type="web",
        discovery_mode="web_keyword",
        keyword="test",
        discovery_limit=1,
    )
    assert source1.discovery_limit == 1

    # Maximum
    source2 = SourceCreate(
        type="web",
        discovery_mode="web_keyword",
        keyword="test",
        discovery_limit=50,
    )
    assert source2.discovery_limit == 50


@pytest.mark.regression
def test_source_with_keyword_null_url() -> None:
    """Keyword sources can have empty URL."""
    source = SourceCreate(
        type="youtube",
        title="Search Results",
        url="",  # Empty is valid for keyword sources
        discovery_mode="keyword",
        keyword="coding tutorials",
    )
    assert source.url == ""
    assert source.keyword == "coding tutorials"


@pytest.mark.regression
def test_discovery_mode_default_none() -> None:
    """discovery_mode defaults to None."""
    source = SourceCreate(
        type="youtube",
        title="Test",
        url="https://youtube.com/watch?v=abc",
    )
    assert source.discovery_mode is None


@pytest.mark.regression
def test_discovery_limit_default_25() -> None:
    """discovery_limit defaults to 25."""
    source = SourceCreate(
        type="web",
        discovery_mode="web_keyword",
        keyword="test",
    )
    assert source.discovery_limit == 25
