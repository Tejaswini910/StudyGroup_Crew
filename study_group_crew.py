"""A small, offline-first, four-agent study group powered by LangChain tools."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.tools import tool


@dataclass(frozen=True)
class AgentProfile:
    name: str
    role: str
    goal: str
    backstory: str


@dataclass(frozen=True)
class Source:
    source_id: str
    title: str
    authors: str
    year: int
    url: str
    summary: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class Claim:
    claim_id: str
    text: str
    source_ids: tuple[str, ...]
    quiz_question: str
    correct_answer: str
    distractors: tuple[str, str]


PROFILES = (
    AgentProfile(
        name="Mira Patel",
        role="Topic Researcher",
        goal="Find concise, relevant evidence and preserve its source trail.",
        backstory=(
            "A learning-science librarian who turns dense papers into careful notes; "
            "she would rather flag a boundary than overstate a result."
        ),
    ),
    AgentProfile(
        name="Theo Brooks",
        role="Quiz Maker",
        goal="Turn each supported research claim into a check for understanding.",
        backstory=(
            "A formative-assessment designer who writes questions to reveal "
            "misconceptions, not just reward familiar wording."
        ),
    ),
    AgentProfile(
        name="Lina Okafor",
        role="Explainer",
        goal="Connect the evidence to a short, usable study routine.",
        backstory=(
            "A peer tutor who has learned to explain one idea at a time and to "
            "separate practical advice from what a study directly tested."
        ),
    ),
    AgentProfile(
        name="Sam Rivera",
        role="Fact-Checker",
        goal="Check that every report claim and quiz key traces to supplied evidence.",
        backstory=(
            "A meticulous science editor who checks source IDs and answer keys "
            "before anything is shared with a study group."
        ),
    ),
)

SOURCES = {
    "S1": Source(
        source_id="S1",
        title="Test-Enhanced Learning: Taking Memory Tests Improves Long-Term Retention",
        authors="Henry L. Roediger III and Jeffrey D. Karpicke",
        year=2006,
        url="https://doi.org/10.1111/j.1467-9280.2006.01693.x",
        summary=(
            "In experiments with prose passages, retrieval practice improved "
            "retention after a delay compared with repeated study, even though "
            "repeated study could perform better on an immediate test."
        ),
        tags=("retrieval", "testing", "memory", "retention", "practice"),
    ),
    "S2": Source(
        source_id="S2",
        title="Improving Students' Learning With Effective Learning Techniques",
        authors=(
            "John Dunlosky, Katherine A. Rawson, Elizabeth J. Marsh, "
            "Mitchell J. Nathan, and Daniel T. Willingham"
        ),
        year=2013,
        url="https://doi.org/10.1111/j.1539-6053.2013.01030.x",
        summary=(
            "This review rated practice testing and distributed practice as "
            "high-utility techniques across the reviewed evidence; several "
            "popular alternatives received lower or more limited ratings."
        ),
        tags=("retrieval", "testing", "spacing", "distributed", "practice", "learning"),
    ),
    "S3": Source(
        source_id="S3",
        title="Spacing Effects in Learning: A Temporal Ridgeline of Optimal Retention",
        authors=(
            "Nicholas J. Cepeda, Harold Pashler, Edward Vul, John T. Wixted, "
            "and Doug Rohrer"
        ),
        year=2008,
        url="https://doi.org/10.1111/j.1467-9280.2008.02209.x",
        summary=(
            "Across distributed-practice experiments, the interval that best "
            "supported later recall generally increased as the desired "
            "retention interval increased."
        ),
        tags=("spacing", "distributed", "interval", "retention", "practice"),
    ),
}

CLAIMS = (
    Claim(
        claim_id="C1",
        text=(
            "For the prose-learning experiments reviewed here, retrieval practice "
            "supported better delayed retention than repeated study; the "
            "immediate-test comparison could favor repeated study."
        ),
        source_ids=("S1",),
        quiz_question="In the cited prose-learning experiments, which method better supported delayed retention?",
        correct_answer="Retrieval practice (taking a memory test).",
        distractors=("Repeated study in every test condition.", "Neither method was compared."),
    ),
    Claim(
        claim_id="C2",
        text=(
            "A major review rated practice testing and distributed practice "
            "as high-utility learning techniques."
        ),
        source_ids=("S2",),
        quiz_question="Which pair did the review rate as high-utility techniques?",
        correct_answer="Practice testing and distributed practice.",
        distractors=("Highlighting and rereading only.", "Studying once and cramming."),
    ),
    Claim(
        claim_id="C3",
        text=(
            "The useful gap between practice sessions depends partly on how long "
            "you need to retain the material; longer desired retention generally "
            "calls for a longer optimal gap."
        ),
        source_ids=("S3",),
        quiz_question="What happens to the generally optimal practice gap as the desired retention period grows?",
        correct_answer="It generally grows as well.",
        distractors=("It always shrinks to zero.", "It is unrelated to the retention period."),
    ),
)


@tool
def lookup_study_sources(topic: str) -> str:
    """Retrieve curated, DOI-linked learning-science sources relevant to a study topic."""
    terms = {word.lower().strip(".,?!") for word in topic.split()}
    study_terms = {
        "study", "studying", "learning", "memory", "practice", "retrieval",
        "spacing", "spaced", "repetition", "testing", "distributed", "interval",
        "retention", "strategies", "exam", "review",
    }
    if not terms.intersection(study_terms):
        return json.dumps({"error": "This demo's curated library covers study and learning strategies only."})

    selected = [source for source in SOURCES.values() if terms.intersection(source.tags)]
    if not selected:
        selected = list(SOURCES.values())
    return json.dumps([asdict(source) for source in selected], ensure_ascii=False)


@tool
def draft_quiz(claims_json: str) -> str:
    """Create multiple-choice questions from the supplied researched claim records."""
    claim_records = json.loads(claims_json)
    questions = []
    for claim in claim_records:
        answers = [claim["correct_answer"], *claim["distractors"]]
        questions.append(
            {
                "claim_id": claim["claim_id"],
                "question": claim["quiz_question"],
                "options": answers,
                "answer": claim["correct_answer"],
                "source_ids": claim["source_ids"],
            }
        )
    return json.dumps(questions, ensure_ascii=False)


@tool
def verify_claim_support(claims_json: str) -> str:
    """Check that each claim cites known sources whose catalog records support its claim ID."""
    claim_records = json.loads(claims_json)
    checks = []
    for claim in claim_records:
        catalog_claim = next((item for item in CLAIMS if item.claim_id == claim["claim_id"]), None)
        valid_sources = [source_id for source_id in claim["source_ids"] if source_id in SOURCES]
        expected_sources = list(catalog_claim.source_ids) if catalog_claim else []
        sources_match = valid_sources == expected_sources
        checks.append(
            {
                "claim_id": claim["claim_id"],
                "supported": bool(valid_sources) and sources_match,
                "source_ids": valid_sources,
                "note": "Citation matches the curated claim." if sources_match else "Citation is missing, unknown, or mismatched.",
            }
        )
    return json.dumps(checks, ensure_ascii=False)


class TopicResearcher:
    profile = PROFILES[0]

    def run(self, topic: str, context: dict[str, Any]) -> None:
        raw_sources = lookup_study_sources.invoke({"topic": topic})
        records = json.loads(raw_sources)
        if isinstance(records, dict) and "error" in records:
            raise ValueError(records["error"])
        context["sources"] = records
        retrieved_ids = {source["source_id"] for source in records}
        context["claims"] = [
            asdict(claim) for claim in CLAIMS if set(claim.source_ids).issubset(retrieved_ids)
        ]
        if not context["claims"]:
            raise ValueError("No curated claims matched the retrieved sources for this topic.")
        context["tool_log"].append(f"lookup_study_sources: retrieved {len(records)} DOI-linked sources")
        context["handoffs"].append("Topic Researcher -> Quiz Maker and Explainer: sources, claims, and citations")


class QuizMaker:
    profile = PROFILES[1]

    def run(self, context: dict[str, Any]) -> None:
        context["quiz"] = json.loads(draft_quiz.invoke({"claims_json": json.dumps(context["claims"])}))
        context["tool_log"].append(f"draft_quiz: created {len(context['quiz'])} questions from researched claims")
        context["handoffs"].append("Quiz Maker -> Fact-Checker: questions, answer keys, and source IDs")


class Explainer:
    profile = PROFILES[2]

    def run(self, context: dict[str, Any]) -> None:
        claim_ids = {claim["claim_id"] for claim in context["claims"]}
        guidance = []
        if "C1" in claim_ids:
            guidance.append(
                "For long-term recall, try retrieving information from memory "
                "before checking your notes; immediate-test results may differ."
            )
        if "C2" in claim_ids:
            guidance.append("Include practice testing and distributed practice in your study routine.")
        if "C3" in claim_ids:
            guidance.append(
                "Space sessions over time, with the gap informed by how long "
                "you need to retain the material."
            )
        context["explanation"] = " ".join(guidance)
        context["explanation_claim_ids"] = [claim["claim_id"] for claim in context["claims"]]
        context["handoffs"].append(
            "Explainer -> Fact-Checker: plain-language guidance linked to "
            + ", ".join(context["explanation_claim_ids"])
        )


class FactChecker:
    profile = PROFILES[3]

    def run(self, context: dict[str, Any]) -> None:
        context["fact_checks"] = json.loads(
            verify_claim_support.invoke({"claims_json": json.dumps(context["claims"] + [
                {"claim_id": question["claim_id"], "source_ids": question["source_ids"]}
                for question in context["quiz"]
            ])})
        )
        context["tool_log"].append(f"verify_claim_support: checked {len(context['fact_checks'])} claims and quiz items")
        known_source_ids = {source["source_id"] for source in context["sources"]}
        quiz_checks = [
            question["answer"] in question["options"]
            and bool(set(question["source_ids"]).intersection(known_source_ids))
            for question in context["quiz"]
        ]
        checks_pass = all(item["supported"] for item in context["fact_checks"]) and all(quiz_checks)
        context["fact_check_passed"] = checks_pass
        context["handoffs"].append(
            "Fact-Checker -> Study Group: " + ("all claim and quiz checks passed" if checks_pass else "review required")
        )
        if not checks_pass:
            raise ValueError("Fact-check failed: at least one claim or quiz answer lacks a source match.")


def _source_map(sources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {source["source_id"]: source for source in sources}


def render_report(topic: str, context: dict[str, Any]) -> str:
    sources = _source_map(context["sources"])
    lines = [
        "# Study Group Crew Report",
        "",
        f"**Topic:** {topic}",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## The Crew",
        "",
    ]
    for profile in PROFILES:
        lines.extend([
            f"### {profile.role}: {profile.name}",
            f"**Goal:** {profile.goal}",
            f"**Backstory:** {profile.backstory}",
            "",
        ])

    lines.extend(["## Research Notes", ""])
    for claim in context["claims"]:
        citations = ", ".join(f"[{source_id}]" for source_id in claim["source_ids"])
        lines.append(f"- **{claim['claim_id']}** {claim['text']} {citations}")
    lines.extend(["", "### Sources", ""])
    for source in context["sources"]:
        lines.append(
            f"- **[{source['source_id']}]** {source['authors']} ({source['year']}). "
            f"[{source['title']}]({source['url']}). {source['summary']}"
        )

    lines.extend(["", "## Peer Explanation", "", context["explanation"], "", "**Evidence links:** "
                  + ", ".join(context["explanation_claim_ids"]), "", "## Retrieval-Practice Quiz", ""])
    for index, question in enumerate(context["quiz"], start=1):
        lines.append(f"{index}. {question['question']}")
        lines.extend(f"   - {letter}. {option}" for letter, option in zip("ABC", question["options"]))
        lines.append(f"   - **Answer:** {question['answer']} ({', '.join(question['source_ids'])})")
        lines.append("")

    lines.extend(["## Fact-Check", "", "**Overall:** PASS" if context["fact_check_passed"] else "**Overall:** FAIL", ""])
    for check in context["fact_checks"]:
        result = "PASS" if check["supported"] else "FAIL"
        lines.append(f"- {result}: {check['claim_id']} -> {', '.join(check['source_ids']) or 'no source'}; {check['note']}")
    lines.extend(["", "## LangChain Tool Calls", ""])
    lines.extend(f"- `{entry}`" for entry in context["tool_log"])
    lines.extend(["", "## Context Handoffs", ""])
    lines.extend(f"- {handoff}" for handoff in context["handoffs"])
    lines.extend(["", "---", "Generated by `study_group_crew.py`. The source summaries are concise study notes; consult the linked papers for full methods and limitations.", ""])
    return "\n".join(lines)


def run_crew(topic: str) -> dict[str, Any]:
    context: dict[str, Any] = {"topic": topic, "tool_log": [], "handoffs": []}
    TopicResearcher().run(topic, context)
    QuizMaker().run(context)
    Explainer().run(context)
    FactChecker().run(context)
    return context


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline LangChain study group crew.")
    parser.add_argument("--topic", default="effective study strategies", help="A study/learning topic (default: effective study strategies).")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "outputs" / "study_group_output.md",
        help="Report path (default: outputs/study_group_output.md).",
    )
    args = parser.parse_args()

    context = run_crew(args.topic)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(args.topic, context), encoding="utf-8")
    print(f"Study group complete: {args.output.resolve()}")
    print(f"Fact-check: {'PASS' if context['fact_check_passed'] else 'FAIL'}")
    print(f"LangChain tools used: {len(context['tool_log'])}")


if __name__ == "__main__":
    main()
