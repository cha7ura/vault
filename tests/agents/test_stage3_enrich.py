from unittest.mock import patch
from scripts.agents.stage3_enrich import (
    build_person_search_query,
    build_study_search_query,
    build_book_search_query,
    extract_profile_from_search,
)


def test_build_person_search_query():
    q = build_person_search_query("Dr. Andrew Huberman", "neuroscience")
    assert "Andrew Huberman" in q
    assert "neuroscience" in q


def test_build_person_search_query_no_expertise():
    q = build_person_search_query("Dr. Andrew Huberman")
    assert "Andrew Huberman" in q


def test_build_study_search_query():
    q = build_study_search_query("Sramek et al.", "cold exposure brown fat")
    assert "Sramek" in q
    assert "cold exposure" in q
    assert "pubmed" in q


def test_build_book_search_query():
    q = build_book_search_query("Why We Sleep", "Matthew Walker")
    assert "Why We Sleep" in q
    assert "Matthew Walker" in q
    assert "goodreads" in q


def test_extract_profile_from_search():
    search_results = [
        {"title": "Andrew Huberman - Wikipedia", "url": "https://en.wikipedia.org/wiki/Andrew_Huberman", "content": "American neuroscientist and tenured professor at Stanford."},
        {"title": "Huberman Lab", "url": "https://hubermanlab.com", "content": "Podcast about science and health."},
    ]

    with patch("scripts.agents.stage3_enrich.llm_json_call") as mock_llm:
        mock_llm.return_value = {
            "bio": "American neuroscientist at Stanford",
            "credentials": "PhD, Stanford Professor",
            "expertise_domains": ["neuroscience"],
        }
        result = extract_profile_from_search("Dr. Andrew Huberman", search_results)

    assert result["bio"] == "American neuroscientist at Stanford"
    assert "neuroscience" in result["expertise_domains"]
