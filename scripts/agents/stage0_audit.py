"""Stage 0 — AUDIT: Identify episode type, guest names, speaker count before pipeline."""
from __future__ import annotations

import re
from scripts.agents.config import DOAC_HOST_NAME
from scripts.agents.db import fetch_all, fetch_one, execute


# ---------------------------------------------------------------------------
# Regex patterns for guest extraction
# ---------------------------------------------------------------------------

# Capitalized word building blocks — name capture fragments used below.
_NAME_WORD = r'[A-Z][a-z]+'
NAME_2_4 = rf'{_NAME_WORD}(?:\s+{_NAME_WORD}){{1,3}}'   # 2-4 capitalized words
NAME_2_3 = rf'{_NAME_WORD}(?:\s+{_NAME_WORD}){{1,2}}'   # 2-3 capitalized words
NAME_1_3 = rf'{_NAME_WORD}(?:\s+{_NAME_WORD}){{0,2}}'   # 1-3 capitalized words

# From description body — explicit mentions
DESC_EXPLICIT = [
    r'(?:my guest today is|today.s guest is)\s+(.+?)(?:,\s*(?:a |the |an |who )|\n|$)',
    r'(?:joined by|speaking with|talking to|interviewing)\s+(.+?)(?:,\s*(?:a |the |an |who )|\.|\n|$)',
    r'(?:Guest|Featuring)[:\s]+(.+?)(?:,|\.|\n|$)',
    r'(?:sits down with|welcomes)\s+(.+?)(?:,\s*(?:a |the |an |who )|\.|\n|$)',
]

# From description opening — "Name Name is a ..."
DESC_OPENING = [
    rf'^((?:Dr\.?\s+|Professor\s+|Sir\s+|Dame\s+)?{NAME_2_4})\s*(?:\([^)]+\)\s*)?(?:is\s+|was\s+)',
    r'^(?:Serial entrepreneur\s+|Award-winning\s+|Bestselling\s+)?((?:[A-Z]{2,}\s+){1,3}[A-Z]{2,})\s+',
    r'^([A-Z][a-z]+)\s+(?:is\s+(?:a|an|the|one)\s+)',
]

# From title — standard "Name Name: Topic"
TITLE_STANDARD = rf'^({_NAME_WORD} {_NAME_WORD}(?:\s{_NAME_WORD})?)\s*[:|]'

# From title — DOAC-specific patterns
TITLE_EXTRA = [
    rf'with\s+({NAME_2_4})\s*[|]',
    rf'with\s+({NAME_2_4})\s*$',
    rf'\(({NAME_2_4})\)',
    rf':\s*({NAME_2_4})\s*\|',
    rf':\s*({NAME_1_3})\s*\|',
    r'^([A-Z][a-z]+)\s+(?:PREDICTION|DEBATE|REVEALS|SHARES|EXPLAINS)',
    rf'(?:Prof\.?\s+|Dr\.?\s+)({NAME_2_3})',
]

# Solo episode keywords
SOLO_KEYWORDS = [
    'q&a', 'honest q', 'secret', 'lessons learned', 'moments on',
    'best pieces', 'advice that', 'my biggest', 'things i',
    'top 7', 'top 10', 'top 5', 'hacks that', 'hacks for',
]


def extract_guest_regex(title: str, description: str | None) -> tuple[str | None, str]:
    """Try to extract guest name using regex. Returns (name, source)."""
    desc = description or ''

    # 1. Description explicit mentions
    for p in DESC_EXPLICIT:
        m = re.search(p, desc[:500], re.IGNORECASE)
        if m:
            name = m.group(1).strip().rstrip('.')
            if 1 <= len(name.split()) <= 5 and not name[0].islower():
                return name, 'desc_explicit'

    # 2. Description opening name
    for p in DESC_OPENING:
        m = re.search(p, desc[:200])
        if m:
            name = m.group(1).strip().rstrip(',')
            if name.isupper():
                name = name.title()
            if 1 <= len(name.split()) <= 5:
                return name, 'desc_opening'

    # 3. Title standard pattern
    m = re.match(TITLE_STANDARD, title)
    if m:
        return m.group(1), 'title_standard'

    # 4. Title DOAC-specific patterns
    for p in TITLE_EXTRA:
        m = re.search(p, title)
        if m:
            name = m.group(1).strip()
            if 1 <= len(name.split()) <= 5:
                return name, 'title_extra'

    return None, 'none'


def extract_guest_llm(title: str, description: str, transcript: str) -> str | None:
    """Use LLM to extract guest name from description + full transcript."""
    from scripts.agents.llm import llm_call

    prompt = f"""Extract the guest name(s) from this podcast episode. The host is {DOAC_HOST_NAME}.

Title: {title}

Description:
{(description or '')[:1000]}

Transcript:
{transcript[:100000]}

Reply with ONLY the guest's full name (e.g. "Andrew Huberman").
If there are multiple guests, list them separated by commas (e.g. "Andrew Huberman, Peter Attia").
If this is a solo episode with no guest, reply "SOLO".
If you cannot determine the guest, reply "UNKNOWN"."""

    response = llm_call(prompt)
    if not response:
        return None
    response = response.strip().strip('"')
    if response.upper() in ('SOLO', 'UNKNOWN', 'N/A', 'NONE'):
        return None
    return response


def get_transcript(episode_id: str, max_tokens: int = 30000) -> str:
    """Get full transcript as text. Truncates at ~max_tokens chars."""
    all_segments = fetch_all(
        """
        SELECT speaker, text, start_time
        FROM segments
        WHERE episode_id=%s
        ORDER BY position
        """,
        (episode_id,),
    )

    if not all_segments:
        return ""

    lines = []
    char_count = 0
    for seg in all_segments:
        speaker = seg.get("speaker", "?")
        text = seg.get("text", "").strip()
        if text:
            line = f"[{speaker}] {text}"
            char_count += len(line)
            if char_count > max_tokens * 4:  # rough char-to-token ratio
                break
            lines.append(line)
    return "\n".join(lines)


def is_likely_solo(title: str) -> bool:
    """Check if title suggests solo episode."""
    title_lower = title.lower()
    return any(kw in title_lower for kw in SOLO_KEYWORDS)


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------

def audit_episodes(channel_slug: str = 'the-diary-of-a-ceo', use_llm: bool = False):
    """Audit all episodes and classify them."""
    channel = fetch_one("SELECT id FROM channels WHERE slug=%s", (channel_slug,))
    if not channel:
        raise ValueError(f"Channel not found: {channel_slug}")

    eps = fetch_all(
        """
        SELECT id, title, description, published_at, duration_seconds
        FROM episodes
        WHERE channel_id=%s
        ORDER BY published_at NULLS LAST
        """,
        (channel["id"],),
    )

    print(f"Auditing {len(eps)} episodes...")
    print(f"{'#':<4} {'Type':<8} {'Source':<15} {'Guest':<30} {'Title':<55}")
    print("-" * 115)

    stats = {'solo': 0, 'interview': 0, 'unknown': 0, 'multi_guest': 0}
    updates = []

    for i, ep in enumerate(eps, 1):
        title = ep.get("title", "")
        desc = ep.get("description", "")
        episode_id = ep["id"]

        # Step 1: Check if solo
        if is_likely_solo(title):
            ep_type = "solo"
            guest_names = []
            source = "keyword"
            stats['solo'] += 1

        else:
            # Step 2: Try regex
            name, source = extract_guest_regex(title, desc)

            if name:
                guest_names = [n.strip() for n in name.split(',')]
                ep_type = "interview"
                stats['interview'] += 1

            elif use_llm:
                # Step 3: LLM with full transcript
                transcript = get_transcript(episode_id)
                llm_name = extract_guest_llm(title, desc, transcript)
                if llm_name:
                    guest_names = [n.strip() for n in llm_name.split(',')]
                    ep_type = "interview"
                    source = "llm"
                    stats['interview'] += 1
                else:
                    guest_names = []
                    ep_type = "unknown"
                    source = "none"
                    stats['unknown'] += 1
            else:
                guest_names = []
                ep_type = "unknown"
                stats['unknown'] += 1

        if len(guest_names) > 1:
            stats['multi_guest'] += 1

        guest_str = ", ".join(guest_names) if guest_names else "—"
        print(f"{i:<4} {ep_type:<8} {source:<15} {guest_str:<30} {title[:55]}")

        # Build update for episodes table
        updates.append({
            "id": episode_id,
            "episode_type": ep_type,
            "guest_names": guest_names,
            "guest_count": len(guest_names),
            "guest_source": source,
        })

    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"  Interview:    {stats['interview']}")
    print(f"  Solo:         {stats['solo']}")
    print(f"  Multi-guest:  {stats['multi_guest']}")
    print(f"  Unknown:      {stats['unknown']}")
    print(f"  Total:        {len(eps)}")
    print(f"  Coverage:     {100 * (1 - stats['unknown'] / len(eps)):.0f}%")

    return updates


def save_audit(updates: list[dict]):
    """Save audit results to episodes table."""
    saved = 0
    for u in updates:
        execute(
            """
            UPDATE episodes
            SET episode_type=%s, guest_names=%s, guest_count=%s, guest_source=%s
            WHERE id=%s
            """,
            (u["episode_type"], u["guest_names"], u["guest_count"], u["guest_source"], u["id"]),
        )
        saved += 1
    print(f"\nSaved {saved} episode audits to DB")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Audit episodes for guest info")
    parser.add_argument("--llm", action="store_true", help="Use LLM for unknown episodes")
    parser.add_argument("--save", action="store_true", help="Save results to DB")
    parser.add_argument("--limit", type=int, default=0, help="Limit episodes")
    args = parser.parse_args()

    updates = audit_episodes(use_llm=args.llm)
    if args.limit:
        updates = updates[:args.limit]
    if args.save:
        save_audit(updates)
