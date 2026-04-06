# Knowledge Graph Ontology Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current Guest/Host/Topic entity model with a Person-centric, 10-type ontology aligned to schema.org/Wikidata standards, then wipe and re-extract 2 test episodes.

**Architecture:** Rewrite the Pydantic entity/edge type definitions in the vendored Graphiti `podcast_vault` module, update the extraction instructions and canonical edge normalizer, add a seed function to pre-create host+podcast entities, update the frontend graph page for new types, then wipe Neo4j and re-run the pipeline on 2 episodes.

**Tech Stack:** Python/Pydantic (entity+edge models), Graphiti (knowledge graph framework), Neo4j Aura (graph DB), Next.js/react-force-graph-2d (frontend), Groq gpt-oss-20b (LLM), OpenRouter qwen3-embedding-8b (embedder)

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Rewrite | `vendor/graphiti/podcast_vault/entity_types.py` | 10 new entity Pydantic models + ENTITY_TYPES dict |
| Rewrite | `vendor/graphiti/podcast_vault/edge_types.py` | 10 new edge Pydantic models + EDGE_TYPES dict + EDGE_TYPE_MAP |
| Rewrite | `vendor/graphiti/podcast_vault/ingest.py` | New extraction instructions prompt |
| Rewrite | `vendor/graphiti/tests/podcast_vault/test_entity_types.py` | Tests for new entity types |
| Rewrite | `vendor/graphiti/tests/podcast_vault/test_edge_types.py` | Tests for new edge types |
| Modify | `vendor/graphiti/tests/podcast_vault/test_ingest.py` | Update instruction content assertions |
| Modify | `vendor/graphiti/graphiti_core/utils/maintenance/edge_operations.py:52-61` | New canonical edge names |
| Modify | `scripts/agents/stage3_extract.py` | Add `seed_host_and_podcast()` function |
| Modify | `scripts/agents/run_pipeline.py` | Call seed before first extract |
| Modify | `app/[channel]/graph/page.tsx` | New edge type colors, Person-centric labels |
| Modify | `lib/graph.ts` | Add `valid_at` to edge query |

---

### Task 1: Rewrite Entity Types

**Files:**
- Rewrite: `vendor/graphiti/podcast_vault/entity_types.py`
- Rewrite: `vendor/graphiti/tests/podcast_vault/test_entity_types.py`

- [ ] **Step 1: Write the tests**

Write `vendor/graphiti/tests/podcast_vault/test_entity_types.py`:

```python
"""Tests for podcast_vault.entity_types module."""

from pydantic import BaseModel

from podcast_vault.entity_types import (
    ENTITY_TYPES,
    Person,
    Organization,
    Work,
    Concept,
    Event,
    Place,
    Product,
    Resource,
    Method,
    Podcast,
)

# ── Defaults ──────────────────────────────────────────────────────────────────


def test_person_defaults():
    p = Person()
    assert p.expertise is None
    assert p.credentials is None
    assert p.role_context is None


def test_organization_defaults():
    o = Organization()
    assert o.org_type is None
    assert o.industry is None


def test_work_defaults():
    w = Work()
    assert w.work_type is None
    assert w.author is None
    assert w.year is None
    assert w.journal is None
    assert w.doi is None


def test_concept_defaults():
    c = Concept()
    assert c.domain is None


def test_event_defaults():
    e = Event()
    assert e.event_type is None
    assert e.date is None


def test_place_defaults():
    p = Place()
    assert p.place_type is None


def test_product_defaults():
    p = Product()
    assert p.product_type is None


def test_resource_defaults():
    r = Resource()
    assert r.resource_type is None


def test_method_defaults():
    m = Method()
    assert m.category is None
    assert m.difficulty is None


def test_podcast_defaults():
    p = Podcast()
    assert p.host is None


# ── With values ───────────────────────────────────────────────────────────────


def test_person_with_values():
    p = Person(expertise='business', credentials='CEO of Flight Story', role_context='podcast host')
    assert p.expertise == 'business'
    assert p.credentials == 'CEO of Flight Story'
    assert p.role_context == 'podcast host'


def test_organization_with_values():
    o = Organization(org_type='company', industry='food')
    assert o.org_type == 'company'
    assert o.industry == 'food'


def test_work_with_values():
    w = Work(work_type='paper', author='Walker & Stickgold', year='2019', journal='Nature', doi='10.1000/xyz')
    assert w.work_type == 'paper'
    assert w.author == 'Walker & Stickgold'
    assert w.year == '2019'
    assert w.journal == 'Nature'
    assert w.doi == '10.1000/xyz'


def test_work_book_with_values():
    w = Work(work_type='book', author='Matthew Walker')
    assert w.work_type == 'book'
    assert w.author == 'Matthew Walker'
    assert w.journal is None
    assert w.doi is None


def test_event_with_values():
    e = Event(event_type='funding_round', date='2020-03')
    assert e.event_type == 'funding_round'
    assert e.date == '2020-03'


def test_place_with_values():
    p = Place(place_type='city')
    assert p.place_type == 'city'


def test_product_with_values():
    p = Product(product_type='supplement')
    assert p.product_type == 'supplement'


def test_resource_with_values():
    r = Resource(resource_type='energy')
    assert r.resource_type == 'energy'


def test_method_with_values():
    m = Method(category='business', difficulty='intermediate')
    assert m.category == 'business'
    assert m.difficulty == 'intermediate'


def test_podcast_with_values():
    p = Podcast(host='Steven Bartlett')
    assert p.host == 'Steven Bartlett'


# ── BaseModel subclass checks ─────────────────────────────────────────────────


def test_all_entity_types_are_basemodel_subclasses():
    for cls in [Person, Organization, Work, Concept, Event, Place, Product, Resource, Method, Podcast]:
        assert issubclass(cls, BaseModel), f'{cls.__name__} must be a BaseModel subclass'


def test_all_entity_types_instantiate_with_no_args():
    for cls in [Person, Organization, Work, Concept, Event, Place, Product, Resource, Method, Podcast]:
        instance = cls()
        assert instance is not None, f'{cls.__name__} must instantiate with no args'


# ── ENTITY_TYPES dict ─────────────────────────────────────────────────────────


def test_entity_types_dict_has_expected_keys():
    expected = {'Person', 'Organization', 'Work', 'Concept', 'Event', 'Place', 'Product', 'Resource', 'Method', 'Podcast'}
    assert set(ENTITY_TYPES.keys()) == expected


def test_entity_types_dict_values_match_classes():
    assert ENTITY_TYPES['Person'] is Person
    assert ENTITY_TYPES['Organization'] is Organization
    assert ENTITY_TYPES['Work'] is Work
    assert ENTITY_TYPES['Concept'] is Concept
    assert ENTITY_TYPES['Event'] is Event
    assert ENTITY_TYPES['Place'] is Place
    assert ENTITY_TYPES['Product'] is Product
    assert ENTITY_TYPES['Resource'] is Resource
    assert ENTITY_TYPES['Method'] is Method
    assert ENTITY_TYPES['Podcast'] is Podcast


def test_entity_types_dict_values_are_basemodel_subclasses():
    for name, cls in ENTITY_TYPES.items():
        assert issubclass(cls, BaseModel), f'ENTITY_TYPES[{name!r}] must be a BaseModel subclass'


def test_entity_types_count_is_10():
    assert len(ENTITY_TYPES) == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd vendor/graphiti && python -m pytest tests/podcast_vault/test_entity_types.py -v 2>&1 | head -30`
Expected: FAIL — cannot import Person, Organization, etc.

- [ ] **Step 3: Write the entity types implementation**

Write `vendor/graphiti/podcast_vault/entity_types.py`:

```python
from pydantic import BaseModel, Field


class Person(BaseModel):
    """Any person mentioned — host, guest, team member, or someone referenced."""
    expertise: str | None = Field(default=None, description='Primary field')
    credentials: str | None = Field(default=None, description='PhD, CEO of X, author, etc.')
    role_context: str | None = Field(default=None, description='Brief: podcast host, social media manager, neuroscientist')


class Organization(BaseModel):
    """Company, university, research lab, government body, NGO, media org."""
    org_type: str | None = Field(default=None, description='company, university, research_lab, government, ngo, media, fund')
    industry: str | None = Field(default=None, description='tech, health, food, finance, media, social_media')


class Work(BaseModel):
    """Book, scientific paper, article, report — any intellectual/creative work."""
    work_type: str | None = Field(default=None, description='book, paper, article, report')
    author: str | None = Field(default=None, description='Author name(s)')
    year: str | None = Field(default=None, description='Publication year')
    journal: str | None = Field(default=None, description='Journal name (papers only)')
    doi: str | None = Field(default=None, description='DOI (papers only)')


class Concept(BaseModel):
    """Subject area, theory, framework, mental model discussed."""
    domain: str | None = Field(default=None, description='health, neuroscience, psychology, fitness, nutrition, business, relationships, productivity')


class Event(BaseModel):
    """A specific occurrence — conference, funding round, product launch, crisis."""
    event_type: str | None = Field(default=None, description='conference, funding_round, launch, crisis, appearance')
    date: str | None = Field(default=None, description='When it happened, if mentioned')


class Place(BaseModel):
    """Geographic location — city, country, venue, region."""
    place_type: str | None = Field(default=None, description='city, country, venue, region')


class Product(BaseModel):
    """Supplement, device, app, tool, platform, vehicle, food product."""
    product_type: str | None = Field(default=None, description='device, app, supplement, tool, platform, vehicle, food')


class Resource(BaseModel):
    """Physical resource — commodity, energy source, capital."""
    resource_type: str | None = Field(default=None, description='commodity, energy, data, capital')


class Method(BaseModel):
    """Actionable routine, protocol, framework, strategy."""
    category: str | None = Field(default=None, description='sleep, exercise, nutrition, cold_exposure, breathing, meditation, business')
    difficulty: str | None = Field(default=None, description='beginner, intermediate, advanced')


class Podcast(BaseModel):
    """A podcast show (the series, not an episode)."""
    host: str | None = Field(default=None, description='Primary host name')


ENTITY_TYPES: dict[str, type[BaseModel]] = {
    'Person': Person,
    'Organization': Organization,
    'Work': Work,
    'Concept': Concept,
    'Event': Event,
    'Place': Place,
    'Product': Product,
    'Resource': Resource,
    'Method': Method,
    'Podcast': Podcast,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd vendor/graphiti && python -m pytest tests/podcast_vault/test_entity_types.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd vendor/graphiti && git add podcast_vault/entity_types.py tests/podcast_vault/test_entity_types.py && git commit -m "feat: rewrite entity types to 10-type Person-centric ontology"
```

---

### Task 2: Rewrite Edge Types

**Files:**
- Rewrite: `vendor/graphiti/podcast_vault/edge_types.py`
- Rewrite: `vendor/graphiti/tests/podcast_vault/test_edge_types.py`

- [ ] **Step 1: Write the tests**

Write `vendor/graphiti/tests/podcast_vault/test_edge_types.py`:

```python
"""Tests for podcast_vault.edge_types module."""

from pydantic import BaseModel

from podcast_vault.edge_types import (
    EDGE_TYPE_MAP,
    EDGE_TYPES,
    Hosts,
    AppearsOn,
    WorksWith,
    AffiliatedWith,
    Claims,
    Recommends,
    Describes,
    References,
    Sponsors,
    RelatesTo,
)

# ── Defaults ──────────────────────────────────────────────────────────────────


def test_hosts_defaults():
    h = Hosts()
    assert h.since is None


def test_appears_on_defaults():
    a = AppearsOn()
    assert a.episode_title is None
    assert a.episode_date is None
    assert a.youtube_id is None


def test_works_with_defaults():
    w = WorksWith()
    assert w.role is None


def test_affiliated_with_defaults():
    a = AffiliatedWith()
    assert a.role is None
    assert a.since is None


def test_claims_defaults():
    c = Claims()
    assert c.insight_type is None
    assert c.confidence is None
    assert c.start_time is None
    assert c.end_time is None
    assert c.youtube_url is None


def test_recommends_defaults():
    r = Recommends()
    assert r.strength is None
    assert r.usage is None


def test_describes_defaults():
    d = Describes()
    assert d.start_time is None
    assert d.end_time is None
    assert d.youtube_url is None


def test_references_defaults():
    r = References()
    assert r.context is None


def test_sponsors_defaults():
    s = Sponsors()
    assert s.deal_type is None


def test_relates_to_defaults():
    r = RelatesTo()
    assert r.relationship is None


# ── With values ───────────────────────────────────────────────────────────────


def test_affiliated_with_investor():
    a = AffiliatedWith(role='investor', since='2019')
    assert a.role == 'investor'
    assert a.since == '2019'


def test_affiliated_with_board_member():
    a = AffiliatedWith(role='board_member')
    assert a.role == 'board_member'


def test_claims_with_values():
    c = Claims(
        insight_type='claim', confidence='high',
        start_time='14:23', end_time='16:05',
        youtube_url='https://youtube.com/watch?v=abc&t=863',
    )
    assert c.insight_type == 'claim'
    assert c.youtube_url == 'https://youtube.com/watch?v=abc&t=863'


def test_appears_on_with_values():
    a = AppearsOn(episode_title='Sleep Science', episode_date='2023-01-15', youtube_id='dQw4w9WgXcQ')
    assert a.episode_title == 'Sleep Science'
    assert a.episode_date == '2023-01-15'


def test_sponsors_with_values():
    s = Sponsors(deal_type='ad_read')
    assert s.deal_type == 'ad_read'


# ── BaseModel subclass checks ─────────────────────────────────────────────────


def test_all_edge_types_are_basemodel_subclasses():
    for cls in [Hosts, AppearsOn, WorksWith, AffiliatedWith, Claims, Recommends, Describes, References, Sponsors, RelatesTo]:
        assert issubclass(cls, BaseModel), f'{cls.__name__} must be a BaseModel subclass'


def test_all_edge_types_instantiate_with_no_args():
    for cls in [Hosts, AppearsOn, WorksWith, AffiliatedWith, Claims, Recommends, Describes, References, Sponsors, RelatesTo]:
        instance = cls()
        assert instance is not None, f'{cls.__name__} must instantiate with no args'


# ── EDGE_TYPES dict ───────────────────────────────────────────────────────────


def test_edge_types_dict_has_expected_keys():
    expected = {'Hosts', 'AppearsOn', 'WorksWith', 'AffiliatedWith', 'Claims', 'Recommends', 'Describes', 'References', 'Sponsors', 'RelatesTo'}
    assert set(EDGE_TYPES.keys()) == expected


def test_edge_types_dict_values_match_classes():
    assert EDGE_TYPES['Hosts'] is Hosts
    assert EDGE_TYPES['AppearsOn'] is AppearsOn
    assert EDGE_TYPES['WorksWith'] is WorksWith
    assert EDGE_TYPES['AffiliatedWith'] is AffiliatedWith
    assert EDGE_TYPES['Claims'] is Claims
    assert EDGE_TYPES['Recommends'] is Recommends
    assert EDGE_TYPES['Describes'] is Describes
    assert EDGE_TYPES['References'] is References
    assert EDGE_TYPES['Sponsors'] is Sponsors
    assert EDGE_TYPES['RelatesTo'] is RelatesTo


def test_edge_types_count_is_10():
    assert len(EDGE_TYPES) == 10


# ── EDGE_TYPE_MAP ─────────────────────────────────────────────────────────────


def test_edge_type_map_has_expected_entity_pairs():
    expected_pairs = {
        ('Person', 'Podcast'),
        ('Person', 'Person'),
        ('Person', 'Organization'),
        ('Person', 'Concept'),
        ('Person', 'Product'),
        ('Person', 'Work'),
        ('Person', 'Method'),
        ('Organization', 'Podcast'),
        ('Concept', 'Concept'),
        ('Method', 'Concept'),
        ('Work', 'Concept'),
        ('Product', 'Concept'),
    }
    assert set(EDGE_TYPE_MAP.keys()) == expected_pairs


def test_edge_type_map_person_podcast():
    assert EDGE_TYPE_MAP[('Person', 'Podcast')] == ['Hosts', 'AppearsOn']


def test_edge_type_map_person_organization():
    assert EDGE_TYPE_MAP[('Person', 'Organization')] == ['AffiliatedWith']


def test_edge_type_map_person_work():
    assert EDGE_TYPE_MAP[('Person', 'Work')] == ['Recommends', 'References']


def test_edge_type_map_names_exist_in_edge_types():
    for pair, edge_names in EDGE_TYPE_MAP.items():
        for name in edge_names:
            assert name in EDGE_TYPES, f'{name!r} from EDGE_TYPE_MAP[{pair}] not in EDGE_TYPES'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd vendor/graphiti && python -m pytest tests/podcast_vault/test_edge_types.py -v 2>&1 | head -20`
Expected: FAIL — cannot import Hosts, AffiliatedWith, etc.

- [ ] **Step 3: Write the edge types implementation**

Write `vendor/graphiti/podcast_vault/edge_types.py`:

```python
from pydantic import BaseModel, Field


class Hosts(BaseModel):
    """Person hosts the podcast show."""
    since: str | None = Field(default=None, description='When the host started, e.g. "2017"')


class AppearsOn(BaseModel):
    """Person appears as a guest on the podcast."""
    episode_title: str | None = Field(default=None, description='The specific episode title')
    episode_date: str | None = Field(default=None, description='Publication date of the episode')
    youtube_id: str | None = Field(default=None, description='YouTube video ID')


class WorksWith(BaseModel):
    """Two people work together."""
    role: str | None = Field(default=None, description='team_member, co-founder, business_partner')


class AffiliatedWith(BaseModel):
    """Person has a relationship with an organization."""
    role: str | None = Field(default=None, description='investor, board_member, founder, ceo, employee, advisor, partner')
    since: str | None = Field(default=None, description='When the affiliation started, if mentioned')


class Claims(BaseModel):
    """Person makes a factual claim or gives advice about a concept."""
    insight_type: str | None = Field(default=None, description='claim, advice, tip, warning, recommendation')
    confidence: str | None = Field(default=None, description='high, medium, low')
    start_time: str | None = Field(default=None, description='YouTube timestamp, e.g. "14:23"')
    end_time: str | None = Field(default=None, description='YouTube timestamp, e.g. "16:05"')
    youtube_url: str | None = Field(default=None, description='Full YouTube URL with timestamp')


class Recommends(BaseModel):
    """Person recommends a book, product, or tool."""
    strength: str | None = Field(default=None, description='strong, casual, mentioned')
    usage: str | None = Field(default=None, description='daily, occasionally, for_specific_purpose')


class Describes(BaseModel):
    """Person describes a method, protocol, or routine."""
    start_time: str | None = Field(default=None, description='YouTube timestamp')
    end_time: str | None = Field(default=None, description='YouTube timestamp')
    youtube_url: str | None = Field(default=None, description='Full YouTube URL with timestamp')


class References(BaseModel):
    """Person references or cites a work (study, book, article)."""
    context: str | None = Field(default=None, description='supports_claim, contradicts_claim, background')


class Sponsors(BaseModel):
    """Organization sponsors the podcast."""
    deal_type: str | None = Field(default=None, description='ad_read, title_sponsor, affiliate')


class RelatesTo(BaseModel):
    """Catch-all for cross-type connections."""
    relationship: str | None = Field(default=None, description='causes, improves, inhibits, part_of, requires')


EDGE_TYPES: dict[str, type[BaseModel]] = {
    'Hosts': Hosts,
    'AppearsOn': AppearsOn,
    'WorksWith': WorksWith,
    'AffiliatedWith': AffiliatedWith,
    'Claims': Claims,
    'Recommends': Recommends,
    'Describes': Describes,
    'References': References,
    'Sponsors': Sponsors,
    'RelatesTo': RelatesTo,
}

EDGE_TYPE_MAP: dict[tuple[str, str], list[str]] = {
    ('Person', 'Podcast'): ['Hosts', 'AppearsOn'],
    ('Person', 'Person'): ['WorksWith'],
    ('Person', 'Organization'): ['AffiliatedWith'],
    ('Person', 'Concept'): ['Claims'],
    ('Person', 'Product'): ['Recommends'],
    ('Person', 'Work'): ['Recommends', 'References'],
    ('Person', 'Method'): ['Describes'],
    ('Organization', 'Podcast'): ['Sponsors'],
    ('Concept', 'Concept'): ['RelatesTo'],
    ('Method', 'Concept'): ['RelatesTo'],
    ('Work', 'Concept'): ['RelatesTo'],
    ('Product', 'Concept'): ['RelatesTo'],
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd vendor/graphiti && python -m pytest tests/podcast_vault/test_edge_types.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd vendor/graphiti && git add podcast_vault/edge_types.py tests/podcast_vault/test_edge_types.py && git commit -m "feat: rewrite edge types to 10-type ontology with AffiliatedWith roles"
```

---

### Task 3: Update Extraction Instructions

**Files:**
- Modify: `vendor/graphiti/podcast_vault/ingest.py`
- Modify: `vendor/graphiti/tests/podcast_vault/test_ingest.py`

- [ ] **Step 1: Update the test assertions**

In `vendor/graphiti/tests/podcast_vault/test_ingest.py`, replace lines 25-34:

```python
def test_graphiti_extraction_instructions_contains_entity_section():
    assert 'ENTITY RULES' in GRAPHITI_EXTRACTION_INSTRUCTIONS


def test_graphiti_extraction_instructions_contains_relationship_section():
    assert 'RELATIONSHIP RULES' in GRAPHITI_EXTRACTION_INSTRUCTIONS


def test_graphiti_extraction_instructions_contains_important_section():
    assert 'IMPORTANT' in GRAPHITI_EXTRACTION_INSTRUCTIONS


def test_graphiti_extraction_instructions_mentions_person_not_guest():
    assert 'Person' in GRAPHITI_EXTRACTION_INSTRUCTIONS
    assert 'Do NOT use Guest or Host as entity types' in GRAPHITI_EXTRACTION_INSTRUCTIONS


def test_graphiti_extraction_instructions_mentions_affiliated_with():
    assert 'AffiliatedWith' in GRAPHITI_EXTRACTION_INSTRUCTIONS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd vendor/graphiti && python -m pytest tests/podcast_vault/test_ingest.py -v 2>&1 | head -20`
Expected: FAIL — old instructions contain 'ENTITY EXTRACTION' not 'ENTITY RULES'

- [ ] **Step 3: Rewrite the extraction instructions in ingest.py**

Replace the `GRAPHITI_EXTRACTION_INSTRUCTIONS` string in `vendor/graphiti/podcast_vault/ingest.py`:

```python
GRAPHITI_EXTRACTION_INSTRUCTIONS = """\
You are analyzing podcast episode transcripts. Extract entities and relationships.

ENTITY RULES:
- Every person mentioned is a Person — host, guest, team member, or anyone referenced
- Companies, universities, labs, governments are Organization (use org_type attribute)
- Books and scientific papers are Work (use work_type: book or paper)
- Subject areas and theories are Concept
- Supplements, devices, apps, tools are Product
- Actionable routines are Method
- Specific occurrences (funding rounds, launches) are Event
- Geographic locations are Place
- The podcast show itself is Podcast

RELATIONSHIP RULES (use ONLY these edge types):
- Person hosting the show = Hosts
- Person appearing as guest = AppearsOn (include episode_title in attributes)
- Person working with another person = WorksWith
- Person affiliated with an organization = AffiliatedWith (MUST specify role: investor, board_member, founder, ceo, employee, advisor, partner)
- Person claiming something about a concept = Claims
- Person recommending a book or product = Recommends
- Person describing a method/routine = Describes
- Person citing a study or book = References
- Organization sponsoring the podcast = Sponsors
- Any other connection = RelatesTo

IMPORTANT:
- Do NOT invent new edge types. Pick from the list above.
- Do NOT use Guest or Host as entity types. Everyone is Person.
- For AffiliatedWith edges, the role attribute is required.
- Set valid_at to the episode publication date.\
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd vendor/graphiti && python -m pytest tests/podcast_vault/test_ingest.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd vendor/graphiti && git add podcast_vault/ingest.py tests/podcast_vault/test_ingest.py && git commit -m "feat: rewrite extraction instructions for Person-centric ontology"
```

---

### Task 4: Update Canonical Edge Normalizer

**Files:**
- Modify: `vendor/graphiti/graphiti_core/utils/maintenance/edge_operations.py:52-61`

- [ ] **Step 1: Replace the canonical edges list**

In `vendor/graphiti/graphiti_core/utils/maintenance/edge_operations.py`, replace the `_CANONICAL_EDGES` list (around line 52):

Old:
```python
_CANONICAL_EDGES: list[str] = [
    'MAKES_CLAIM', 'DESCRIBES_PROTOCOL', 'REFERENCES_STUDY',
    'RECOMMENDS_BOOK', 'RECOMMENDS_PRODUCT', 'RELATES_TO',
    'APPEARS_ON', 'SUPPORTS_PROTOCOL',
]
```

New:
```python
_CANONICAL_EDGES: list[str] = [
    'HOSTS', 'APPEARS_ON', 'WORKS_WITH', 'AFFILIATED_WITH',
    'CLAIMS', 'RECOMMENDS', 'DESCRIBES', 'REFERENCES',
    'SPONSORS', 'RELATES_TO',
]
```

- [ ] **Step 2: Verify the normalizer still works**

Run: `cd vendor/graphiti && python -c "
from graphiti_core.utils.maintenance.edge_operations import _normalize_edge_name
assert _normalize_edge_name('AffiliatedWith') == 'AFFILIATED_WITH'
assert _normalize_edge_name('CLAIMS') == 'CLAIMS'
assert _normalize_edge_name('WorksWith') == 'WORKS_WITH'
assert _normalize_edge_name('Hosts') == 'HOSTS'
assert _normalize_edge_name('AFFILIATEDWITH') == 'AFFILIATED_WITH'
print('All normalizer checks pass')
"`
Expected: "All normalizer checks pass"

- [ ] **Step 3: Commit**

```bash
cd vendor/graphiti && git add graphiti_core/utils/maintenance/edge_operations.py && git commit -m "feat: update canonical edge names for new ontology"
```

---

### Task 5: Add Seed Function to Pipeline

**Files:**
- Modify: `scripts/agents/stage3_extract.py`
- Modify: `scripts/agents/run_pipeline.py`

- [ ] **Step 1: Add `seed_host_and_podcast()` to stage3_extract.py**

Add this function after the imports section (after line 39) in `scripts/agents/stage3_extract.py`:

```python
async def seed_host_and_podcast(
    host_name: str,
    host_bio: str,
    podcast_name: str,
    podcast_description: str,
    first_episode_date: str | None,
):
    """Pre-create host and podcast entities so episodes link to them correctly."""
    import time as _time
    from graphiti_core import Graphiti
    from graphiti_core.llm_client import OpenAIClient, LLMConfig
    from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.driver.neo4j_driver import Neo4jDriver

    llm_config = LLMConfig(
        api_key=LLM_API_KEY, base_url=LLM_BASE_URL,
        model=LLM_MODEL, small_model=LLM_MODEL,
    )
    llm_client = OpenAIClient(llm_config)
    embedder = OpenAIEmbedder(OpenAIEmbedderConfig(
        api_key=LLM_API_KEY, base_url=LLM_BASE_URL,
    ))
    graph_driver = Neo4jDriver(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, database=NEO4J_DATABASE)

    graphiti = Graphiti(llm_client=llm_client, embedder=embedder, graph_driver=graph_driver)

    ref_time = datetime.fromisoformat(first_episode_date) if first_episode_date else datetime.now(timezone.utc)

    seed_body = f"""{host_name} is a person who hosts {podcast_name}. {host_bio}

{podcast_name}: {podcast_description}

{host_name} hosts {podcast_name}."""

    try:
        t0 = _time.time()
        await graphiti.add_episode(
            name=f"seed-{podcast_name.lower().replace(' ', '-')}",
            episode_body=seed_body,
            source_description=f"Seed profile for {podcast_name} hosted by {host_name}",
            group_id=build_group_id(podcast_name),
            entity_types=ENTITY_TYPES,
            edge_types=EDGE_TYPES,
            edge_type_map=EDGE_TYPE_MAP,
            custom_extraction_instructions=GRAPHITI_EXTRACTION_INSTRUCTIONS,
            reference_time=ref_time,
        )
        print(f"    Seeded host + podcast in {_time.time() - t0:.1f}s")
    finally:
        await graphiti.close()
```

- [ ] **Step 2: Add seed call to run_pipeline.py**

In `scripts/agents/run_pipeline.py`, add the import at line 11:

```python
from scripts.agents.stage3_extract import extract_episode, seed_host_and_podcast
```

Then modify `run_stage3` to accept `channel_slug` and call seed before first episode:

```python
def run_stage3(episodes: list[dict], prep_results: dict, channel_slug: str = DOAC_CHANNEL_SLUG):
    """Run Stage 3 EXTRACT for all episodes."""
    print(f"\n{'='*60}")
    print(f"STAGE 3 — EXTRACT ({len(episodes)} episodes)")
    print(f"{'='*60}\n")

    # Seed host + podcast entities once before first episode
    if channel_slug == DOAC_CHANNEL_SLUG:
        earliest_date = None
        for ep in episodes:
            pa = ep.get("published_at")
            if pa and (not earliest_date or pa < earliest_date):
                earliest_date = pa
        print("Seeding host + podcast profile...")
        asyncio.run(seed_host_and_podcast(
            host_name="Steven Bartlett",
            host_bio="Entrepreneur, investor, author of Happy Sexy Millionaire, "
                     "CEO of Flight Story, former CEO of Social Chain. "
                     "Investor in Huel, sits on the board of Huel.",
            podcast_name="Diary of a CEO",
            podcast_description="The Diary of a CEO is a podcast hosted by Steven Bartlett "
                                "featuring interviews with world-class guests on business, "
                                "health, relationships, and personal development.",
            first_episode_date=earliest_date,
        ))

    for idx, ep in enumerate(episodes, 1):
```

Update the call site at the bottom to pass `channel_slug`:

```python
        run_stage3(episodes, prep_results, channel_slug=args.channel)
```

- [ ] **Step 3: Verify imports work**

Run: `cd /Users/chaturaattidiya/Documents/Github/project-ref/vault && python -c "from scripts.agents.stage3_extract import seed_host_and_podcast; print('import ok')"`
Expected: "import ok"

- [ ] **Step 4: Commit**

```bash
git add scripts/agents/stage3_extract.py scripts/agents/run_pipeline.py && git commit -m "feat: add seed function for host+podcast pre-creation"
```

---

### Task 6: Update Frontend Graph Page

**Files:**
- Modify: `app/[channel]/graph/page.tsx`
- Modify: `lib/graph.ts`

- [ ] **Step 1: Update lib/graph.ts to include valid_at**

In `lib/graph.ts`, update the `GraphEdge` interface:

```typescript
export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  fact: string;
  valid_at?: string;
}
```

Update the edges Cypher query to return `r.valid_at`:

```typescript
      MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
      RETURN a.uuid AS source, b.uuid AS target, r.name AS type, r.fact AS fact, r.valid_at AS valid_at
```

Update the edges map to include `valid_at`:

```typescript
    const edges: GraphEdge[] = edgesResult.records.map(r => {
      const va = r.get('valid_at');
      return {
        source: r.get('source'),
        target: r.get('target'),
        type: r.get('type'),
        fact: r.get('fact'),
        valid_at: va ? va.toString() : undefined,
      };
    });
```

- [ ] **Step 2: Update graph page edge colors and types**

In `app/[channel]/graph/page.tsx`, replace the `TYPE_COLORS` object:

```typescript
const TYPE_COLORS: Record<string, string> = {
  HOSTS: '#60a5fa',
  APPEARS_ON: '#818cf8',
  WORKS_WITH: '#eab308',
  AFFILIATED_WITH: '#14b8a6',
  CLAIMS: '#ef4444',
  RECOMMENDS: '#f97316',
  DESCRIBES: '#10b981',
  REFERENCES: '#06b6d4',
  SPONSORS: '#f59e0b',
  RELATES_TO: '#6b7280',
};
```

Update the `GraphEdge` interface to add `valid_at`:

```typescript
interface GraphEdge {
  source: string;
  target: string;
  type: string;
  fact: string;
  valid_at?: string;
}
```

In the sidebar edge card, add valid_at display after the fact line:

```tsx
{e.fact && <p className="text-xs text-zinc-500">{e.fact}</p>}
{e.valid_at && (
  <p className="text-xs text-zinc-600 mt-1">
    {new Date(e.valid_at).toLocaleDateString()}
  </p>
)}
```

Update the node label display to show "Person" labels instead of "Host"/"Guest":

In the sidebar where labels are displayed (`selected.labels.filter(l => l !== 'Entity').join(', ')`), this already works — it will now show "Person", "Organization", etc.

- [ ] **Step 3: Verify the page compiles**

Run: `curl -s -m 30 http://localhost:3020/api/health` (assuming dev server is running)
Expected: `{"ok":true}`

- [ ] **Step 4: Commit**

```bash
git add lib/graph.ts app/\\[channel\\]/graph/page.tsx && git commit -m "feat: update graph page for new ontology edge types and colors"
```

---

### Task 7: Wipe Neo4j and Re-extract

**Files:** No code changes — operational steps.

- [ ] **Step 1: Wipe all existing Neo4j data**

```bash
node -e "
const neo4j = require('neo4j-driver');
const driver = neo4j.driver(
  process.env.NEO4J_URI,
  neo4j.auth.basic(process.env.NEO4J_USERNAME, process.env.NEO4J_PASSWORD)
);
const session = driver.session({ database: process.env.NEO4J_DATABASE });
session.run('MATCH (n) DETACH DELETE n').then(r => {
  console.log('Wiped all nodes and edges');
  return session.run('MATCH (n) RETURN count(n) AS c');
}).then(r => {
  console.log('Remaining nodes:', r.records[0].get('c').toNumber());
  session.close().then(() => driver.close());
}).catch(e => { console.error(e); session.close().then(() => driver.close()); });
"
```
Expected: "Wiped all nodes and edges", "Remaining nodes: 0"

- [ ] **Step 2: Reset knowledge_processed_at for test episodes**

```bash
python -c "
from scripts.agents.config import get_supabase
sb = get_supabase()
# Clear the processed flag on all episodes so they get re-extracted
sb.table('episodes').update({'knowledge_processed_at': None}).neq('id', '').execute()
print('Reset knowledge_processed_at on all episodes')
"
```

- [ ] **Step 3: Run pipeline extract on 2 episodes**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault
python -m scripts.agents.run_pipeline --stage extract --limit 2
```

Expected: Seed runs first, then 2 episodes extract with new ontology types.

- [ ] **Step 4: Verify data quality**

```bash
node -e "
const neo4j = require('neo4j-driver');
const driver = neo4j.driver(
  process.env.NEO4J_URI,
  neo4j.auth.basic(process.env.NEO4J_USERNAME, process.env.NEO4J_PASSWORD)
);
const session = driver.session({ database: process.env.NEO4J_DATABASE });
session.run('MATCH (n:Entity) RETURN labels(n) AS labels, count(*) AS c ORDER BY c DESC').then(r => {
  console.log('=== ENTITY LABELS ===');
  r.records.forEach(rec => console.log(rec.get('labels').join(', '), ':', rec.get('c').toNumber()));
  return session.run('MATCH ()-[r:RELATES_TO]->() RETURN r.name AS type, count(*) AS c ORDER BY c DESC');
}).then(r => {
  console.log('\\n=== EDGE TYPES ===');
  r.records.forEach(rec => console.log(rec.get('type'), ':', rec.get('c').toNumber()));
  session.close().then(() => driver.close());
}).catch(e => { console.error(e); session.close().then(() => driver.close()); });
"
```

Expected:
- Entity labels should show: `Entity, Person`, `Entity, Organization`, `Entity, Concept`, `Entity, Product`, `Entity, Method`, `Entity, Podcast` — NO `Guest` or `Host` labels
- Edge types should only show: `HOSTS`, `APPEARS_ON`, `WORKS_WITH`, `AFFILIATED_WITH`, `CLAIMS`, `RECOMMENDS`, `DESCRIBES`, `REFERENCES`, `SPONSORS`, `RELATES_TO` — NO fragmented types like `SPONSOR_OF` or one-off hallucinated types

- [ ] **Step 5: Check Steven Bartlett is Person with correct edges**

```bash
node -e "
const neo4j = require('neo4j-driver');
const driver = neo4j.driver(
  process.env.NEO4J_URI,
  neo4j.auth.basic(process.env.NEO4J_USERNAME, process.env.NEO4J_PASSWORD)
);
const session = driver.session({ database: process.env.NEO4J_DATABASE });
session.run('MATCH (p:Entity {name: \"Steven Bartlett\"}) RETURN labels(p) AS labels, p.summary AS summary').then(r => {
  const rec = r.records[0];
  console.log('Labels:', rec.get('labels'));
  console.log('Summary:', (rec.get('summary') || '').substring(0, 150));
  return session.run('MATCH (p:Entity {name: \"Steven Bartlett\"})-[r:RELATES_TO]->(t) RETURN r.name AS type, t.name AS target, labels(t) AS target_labels LIMIT 15');
}).then(r => {
  console.log('\\nEdges:');
  r.records.forEach(rec => console.log(' ', rec.get('type'), '->', rec.get('target'), rec.get('target_labels').filter(l => l !== 'Entity')));
  session.close().then(() => driver.close());
}).catch(e => { console.error(e); session.close().then(() => driver.close()); });
"
```

Expected: Labels should include `Person` (not `Host` or `Guest`). Edges should show `HOSTS -> Diary of a CEO`, `AFFILIATED_WITH -> Huel`, `AFFILIATED_WITH -> Social Chain`, etc.

- [ ] **Step 6: Open graph in browser and verify**

Open: `http://localhost:3020/the-diary-of-a-ceo/graph`

Verify:
- Steven Bartlett labeled as Person
- Huel labeled as Organization (not Product)
- Edge colors match new TYPE_COLORS
- Sidebar shows valid_at dates
- No Guest/Host labels anywhere
