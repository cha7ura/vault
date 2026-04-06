# Knowledge Graph Ontology Redesign

**Date:** 2026-04-06
**Status:** Approved
**Scope:** Entity types, edge types, extraction instructions, seed data, migration

## Problem

The current knowledge graph schema has data quality issues from the first 2 test episodes (43 entities, 52 edges):

1. **Wrong entity labels**: Grace (social media manager) labeled as Guest; Steven Bartlett labeled as Host. Roles should come from edges, not entity types.
2. **No Company/Organization distinction**: Huel is labeled Product but Steven invests in it and sits on its board. Companies and products are conflated.
3. **Fragmented edge types**: SPONSORS, SPONSOR_OF, SPONSORSHIP, HAS_SPONSOR all mean the same thing. LLM hallucinating one-off types like DECIDED_TO_PUBLISH_EVERY_MONDAY.
4. **No temporal aggregation**: Same facts mentioned across episodes aren't collated into unified views.
5. **Unlabeled entities**: "Global marketing director" has no entity type at all.

## Design Principles

- **Person-centric**: Everyone is a Person. Roles (host, guest, team member) are relationships, not labels.
- **Standard ontology terms**: Aligned with schema.org, Wikidata, and SKOS naming conventions.
- **One verb per relationship**: Always from the actor's perspective. No synonyms (Sponsors, not SponsorOf).
- **Attributes over types**: Use sub-type attributes to distinguish variants within an entity type (e.g., Organization.org_type = company | university).
- **Strict canonical set**: Edge types are a closed set. The LLM must pick from the list, not invent new ones.

## Entity Types (10)

| Type | Standard Source | Sub-types (attribute) | Examples |
|---|---|---|---|
| **Person** | schema.org, Wikidata Q5 | — (role_context as free text) | Steven Bartlett, Grace, Julian Hearn, Reggie Yates |
| **Organization** | schema.org, Wikidata Q43229 | `company`, `university`, `research_lab`, `government`, `ngo`, `media`, `fund` | Huel, Social Chain, Stanford, NHS |
| **Work** | Wikidata Q386724 | `book`, `paper`, `article`, `report` | Happy Sexy Millionaire, referenced studies |
| **Concept** | SKOS/schema.org DefinedTerm | `topic`, `theory`, `framework`, `mental_model` | Dopamine, Product-Market Fit, Compound Interest |
| **Event** | schema.org, Wikidata Q1656682 | `conference`, `funding_round`, `launch`, `crisis` | IPO, Dragon's Den appearance |
| **Place** | schema.org, SUMO | `city`, `country`, `venue`, `region` | Manchester, London, Silicon Valley |
| **Product** | schema.org | `device`, `app`, `supplement`, `tool`, `platform`, `vehicle`, `food` | Electric bicycle, Nutribullet, Fiverr, LinkedIn |
| **Resource** | Dublin Core, SUMO | `commodity`, `energy`, `data`, `capital` | Oil, renewable energy |
| **Method** | — | `protocol`, `framework`, `routine`, `strategy` | Cold Email Outreach, Morning Routine |
| **Podcast** | schema.org PodcastSeries | — | Diary of a CEO |

### Entity Pydantic Models

```python
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
```

## Edge Types (10)

| Edge | From → To | What it captures | Key attributes |
|---|---|---|---|
| **Hosts** | Person → Podcast | Person hosts the show | `since` |
| **AppearsOn** | Person → Podcast | Guest appeared on episode | `episode_title`, `episode_date`, `youtube_id` |
| **WorksWith** | Person → Person | Team, collaborators, co-founders | `role` (team_member, co-founder, business_partner) |
| **AffiliatedWith** | Person → Organization | Any person-org relationship | `role` (investor, board_member, founder, ceo, employee, advisor, partner) |
| **Claims** | Person → Concept | Person makes a claim about a topic | `insight_type`, `confidence`, `start_time`, `end_time`, `youtube_url` |
| **Recommends** | Person → Work/Product | Recommends a book, product, tool | `strength` (strong, casual, mentioned), `usage` |
| **Describes** | Person → Method | Person describes a protocol/framework | `start_time`, `end_time`, `youtube_url` |
| **References** | Person → Work | Person cites a study or book | `context` (supports_claim, contradicts_claim, background) |
| **Sponsors** | Organization → Podcast | Org sponsors the podcast | `deal_type` (ad_read, title_sponsor, affiliate) |
| **RelatesTo** | any → any | Catch-all for cross-type connections | `relationship` (causes, improves, inhibits, part_of, requires) |

### Edge Pydantic Models

```python
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
```

### Edge Type Map

```python
EDGE_TYPE_MAP = {
    # Person edges
    ('Person', 'Podcast'):      ['Hosts', 'AppearsOn'],
    ('Person', 'Person'):       ['WorksWith'],
    ('Person', 'Organization'): ['AffiliatedWith'],
    ('Person', 'Concept'):      ['Claims'],
    ('Person', 'Product'):      ['Recommends'],
    ('Person', 'Work'):         ['Recommends', 'References'],
    ('Person', 'Method'):       ['Describes'],
    # Organization edges
    ('Organization', 'Podcast'): ['Sponsors'],
    # Cross-type edges
    ('Concept', 'Concept'):     ['RelatesTo'],
    ('Method', 'Concept'):      ['RelatesTo'],
    ('Work', 'Concept'):        ['RelatesTo'],
    ('Product', 'Concept'):     ['RelatesTo'],
}
```

Unmapped entity pairs fall through to Graphiti's default `RELATES_TO`.

## Canonical Edge Name Normalization

The `_normalize_edge_name()` function in `edge_operations.py` must be updated with the new canonical set:

```python
_CANONICAL_EDGES = [
    'HOSTS', 'APPEARS_ON', 'WORKS_WITH', 'AFFILIATED_WITH',
    'CLAIMS', 'RECOMMENDS', 'DESCRIBES', 'REFERENCES',
    'SPONSORS', 'RELATES_TO',
]
```

Any LLM output that doesn't match these (e.g., `INVESTS_IN`, `SPONSOR_OF`, `CEO_OF`) falls through to `RELATES_TO`.

## Extraction Instructions

```
You are analyzing podcast episode transcripts. Extract entities and relationships.

ENTITY RULES:
- Every person mentioned is a Person — host, guest, team member, or anyone referenced
- Companies, universities, labs, governments are Organization (use org_type attribute)
- Books and scientific papers are Work (use work_type: book or paper)
- Subject areas and theories are Concept
- Supplements, devices, apps, tools are Product
- Actionable routines are Method
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
- Set valid_at to the episode publication date.
```

## Seed Episode

Before processing any episodes for a channel, inject a synthetic seed episode to pre-establish the host and podcast entities with correct types:

```python
async def seed_host_and_podcast(host_name, host_bio, podcast_name, podcast_desc, first_episode_date):
    seed_body = f"""{host_name} is a person who hosts {podcast_name}. {host_bio}

{podcast_name}: {podcast_desc}

{host_name} hosts {podcast_name}."""

    await graphiti.add_episode(
        name=f"seed-{podcast_slug}",
        episode_body=seed_body,
        source_description=f"Seed profile for {podcast_name} hosted by {host_name}",
        group_id=build_group_id(podcast_name),
        entity_types=ENTITY_TYPES,
        edge_types=EDGE_TYPES,
        edge_type_map=EDGE_TYPE_MAP,
        custom_extraction_instructions=EXTRACTION_INSTRUCTIONS,
        reference_time=first_episode_date,
    )
```

For DOAC, the seed includes: Steven Bartlett's bio, his companies (Social Chain, Flight Story), key investments (Huel), and the podcast description.

## Frontend Aggregation Queries

### Person Profile — "Invests In" tab
```cypher
MATCH (p:Person {name: $name})-[r:RELATES_TO]->(o:Organization)
WHERE r.name = 'AFFILIATED_WITH'
RETURN o.name, r.fact, r.valid_at, r.attributes
```
Filter in application layer: `attributes.role = 'investor'` for investments, `attributes.role = 'board_member'` for board seats, etc.

### Person Profile — Guest Appearances
```cypher
MATCH (p:Person {name: $name})-[r:RELATES_TO]->(pod:Podcast)
WHERE r.name = 'APPEARS_ON'
RETURN r.fact, r.valid_at, r.attributes
ORDER BY r.valid_at
```
Multiple appearances = multiple edges with different `valid_at` dates and episode attributes.

### Person Profile — Claims
```cypher
MATCH (p:Person {name: $name})-[r:RELATES_TO]->(c:Concept)
WHERE r.name = 'CLAIMS'
RETURN c.name, r.fact, r.valid_at, r.attributes
ORDER BY r.valid_at DESC
```

### Podcast Sponsors
```cypher
MATCH (o:Organization)-[r:RELATES_TO]->(pod:Podcast)
WHERE r.name = 'SPONSORS'
RETURN o.name, r.fact, r.valid_at
```

## Migration Plan

1. **Wipe existing Neo4j data** — the 2 test episodes will be re-extracted with the new schema
2. **Update entity_types.py** — replace Guest/Host/Topic/Study/Book with new 10-type set
3. **Update edge_types.py** — replace current 8 edge types with new 10-type set
4. **Update ingest.py** — new extraction instructions
5. **Update edge_operations.py** — new canonical edge names
6. **Update stage3_extract.py** — add seed function, split LLM/embedder config
7. **Update run_pipeline.py** — call seed before first episode
8. **Update graph page** — new edge type colors, Person-centric sidebar
9. **Re-process 2 test episodes** — quality check
10. **Process remaining 484 episodes** — full extraction

## Sources

- [Schema.org Thing hierarchy](https://schema.org/Thing)
- [Schema.org Organization](https://schema.org/Organization)
- [Schema.org PodcastSeries](https://schema.org/PodcastSeries)
- [Wikidata Q43229 — Organization](https://www.wikidata.org/wiki/Q43229)
- [Graphiti Custom Entity and Edge Types](https://help.getzep.com/graphiti/core-concepts/custom-entity-and-edge-types)
- [Graphiti Podcast Processing Example](https://deepwiki.com/getzep/graphiti/11.3-basic-usage-examples)
- [SUMO Upper Ontology](https://en.wikipedia.org/wiki/Suggested_Upper_Merged_Ontology)
