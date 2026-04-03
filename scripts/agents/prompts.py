#!/usr/bin/env python3
"""LLM prompt templates and empty memory schema for people agents."""

EMPTY_MEMORY = {
    "persona": {
        "communication_style": {
            "tone": "",
            "formality": "",
            "storytelling_tendency": "",
            "signature_phrases": [],
            "speech_patterns": [],
        },
        "personality_traits": {
            "openness": "",
            "conscientiousness": "",
            "extraversion": "",
            "agreeableness": "",
            "emotional_stability": "",
        },
        "expertise_domains": [],
    },
    "semantic_memory": {
        "beliefs": {},
        "frameworks": [],
        "recurring_themes": [],
        "references": [],
        "relationships": [],
    },
    "episodic_memory": [],
    "reflections": [],
    "contradictions": [],
    "growth_log": [],
}

INTRO_DETECTION_PROMPT = """You are analyzing the start of a podcast episode transcript. Determine where the actual interview/conversation begins (after any intro music, sponsor reads, subscribe prompts).

Transcript (first segments):
{segments_text}

Return ONLY the position number (integer) of the first segment where the real conversation starts. If the conversation starts from the very beginning, return 0."""

GUEST_EXTRACTION_PROMPT = """Extract the guest's full name from this podcast episode description. Return ONLY the name, nothing else. If you cannot determine the guest name, return "UNKNOWN".

Description:
{description}"""

TRIAGE_PROMPT = """You are a transcript analyst. Given a single transcript turn, classify it as either SUBSTANTIVE or FILLER.

FILLER: greetings, acknowledgements, back-channel responses, filler words, very short affirmations with no informational content.
SUBSTANTIVE: anything that contains an opinion, fact, story, question with depth, explanation, or meaningful contribution to the conversation.

Transcript turn:
\"\"\"{text}\"\"\"

Respond with exactly one word: SUBSTANTIVE or FILLER"""

MEMORY_MERGE_PROMPT = """You are a memory curator for a person named {person_name}. Your job is to merge new information from a conversation turn into their existing memory.

CURRENT MEMORY (JSON):
{current_memory}

CONTEXT (recent conversation turns for context):
{context_turns}

NEW TURN by {person_name}:
\"\"\"{new_turn}\"\"\"

Episode: {episode_id}
Date: {episode_date}
Role: {role}

INSTRUCTIONS:
- Merge new information into the existing memory structure. Do NOT simply append — integrate and deduplicate.
- Update confidence levels where applicable.
- Note any contradictions with previously held beliefs or positions in the "contradictions" array.
- Add to "growth_log" ONLY if there is a meaningful shift in perspective, expertise, or personality compared to existing memory.
- Preserve all existing information that is not contradicted.
- Return ONLY the updated JSON memory object, no explanation or commentary.

Updated memory JSON:"""

EPISODE_SUMMARY_PROMPT = """You are summarising a person's contributions to a single podcast episode.

Person: {person_name}
Episode: {episode_id}
Date: {episode_date}

Their substantive turns from this episode:
{turns}

Produce a JSON object with exactly these fields:
- "summary": 2-3 sentence summary of their contributions and key points
- "key_moments": array of up to 3 strings, each describing a notable moment
- "emotional_peaks": array of up to 2 objects, each with "topic" (string) and "reaction" (string)

Return ONLY the JSON object, no explanation or commentary."""
