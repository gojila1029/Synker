"""Tests for the adapter registry."""
from app.adapters.registry import get_adapter
from app.adapters.youtube import YoutubeAdapter
from app.adapters.web import WebAdapter
from app.adapters.pdf import PdfAdapter
from app.adapters.local import LocalAdapter


def test_youtube_adapter():
    assert isinstance(get_adapter("youtube"), YoutubeAdapter)


def test_web_adapter():
    assert isinstance(get_adapter("web"), WebAdapter)


def test_pdf_adapter():
    assert isinstance(get_adapter("pdf"), PdfAdapter)


def test_local_adapter():
    assert isinstance(get_adapter("local"), LocalAdapter)


def test_unknown_returns_none():
    assert get_adapter("unknown_type") is None
