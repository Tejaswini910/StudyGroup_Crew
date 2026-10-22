"""Subject-neutral study workflow with LangChain tools and optional local Ollama."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


@dataclass(frozen=True)
class AgentProfile:
    name: str
    role: str
    goal: str
    backstory: str


PROFILES = (
    AgentProfile(
        name="Mira Patel",
        role="Topic Researcher",
        goal="Gather relevant evidence and keep the source trail attached to every finding.",
        backstory="A research librarian who checks the source before trusting a memorable claim.",
    ),
    AgentProfile(
        name="Lina Okafor",
        role="Study Explainer",
        goal="Turn research and syllabus material into structured, understandable notes.",
        backstory="A patient peer tutor who starts with the big idea, then defines unfamiliar terms.",
    ),
    AgentProfile(
        name="Theo Brooks",
        role="Quiz Maker",
        goal="Create answerable multiple-choice questions with explanations grounded in the notes.",
        backstory="A formative-assessment designer who uses questions to reveal misconceptions.",
    ),
    AgentProfile(
        name="Sam Rivera",
        role="Fact-Checker",
        goal="Verify source references, quiz keys, and explanations before saving study materials.",
        backstory="A careful science editor who distinguishes a citation check from proof of truth.",
    ),
)


@tool
def wikipedia_search(subject: str, topic: str) -> str:
    """Search Wikipedia for a subject and topic, returning page extracts and source URLs."""
    query = " ".join(part.strip() for part in (subject, topic) if part.strip())
    search_params = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "srlimit": 4,
            "utf8": 1,
        }
    )
    headers = {"User-Agent": "StudyGroupCrew/1.0 (educational study assistant)"}
    try:
        search_request = urllib.request.Request(
            f"https://en.wikipedia.org/w/api.php?{search_params}", headers=headers
        )
        with urllib.request.urlopen(search_request, timeout=12) as response:
            search_payload = json.loads(response.read().decode("utf-8"))
        pages = search_payload.get("query", {}).get("search", [])
        if not pages:
            return json.dumps({"results": [], "error": "Wikipedia returned no matching pages."})

        page_ids = [str(page["pageid"]) for page in pages]
        extract_params = urllib.parse.urlencode(
            {
                "action": "query",
                "format": "json",
                "prop": "extracts",
                "explaintext": 1,
                "exintro": 1,
                "exchars": 1800,
                "pageids": "|".join(page_ids),
            }
        )
        extract_request = urllib.request.Request(
            f"https://en.wikipedia.org/w/api.php?{extract_params}", headers=headers
        )
        with urllib.request.urlopen(extract_request, timeout=12) as response:
            extract_payload = json.loads(response.read().decode("utf-8"))
        extract_pages = extract_payload.get("query", {}).get("pages", {})
        results = []
        for index, page in enumerate(pages, start=1):
            extracted = extract_pages.get(str(page["pageid"]), {})
            summary = re.sub(r"\s+", " ", extracted.get("extract", "")).strip()
            if not summary:
                summary = re.sub(r"<[^>]+>", " ", page.get("snippet", ""))
            if summary:
                results.append(
                    {
                        "source_id": f"W{index}",
                        "title": page["title"],
                        "summary": summary[:1800],
                        "url": f"https://en.wikipedia.org/?curid={page['pageid']}",
                        "source_type": "Wikipedia",
                    }
                )
        return json.dumps({"results": results}, ensure_ascii=False)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, OSError) as error:
        return json.dumps({"results": [], "error": f"Wikipedia search unavailable: {error}"})


@tool
def syllabus_content_search(syllabus_text: str, topic: str) -> str:
    """Find syllabus sections that mention a selected topic in user-provided syllabus text."""
    if not syllabus_text.strip():
        return json.dumps({"results": [], "message": "No syllabus text was supplied."})

    sections = [part.strip() for part in re.split(r"\n\s*\n", syllabus_text) if part.strip()]
    if not sections:
        sections = [syllabus_text.strip()]
    stop_words = {"the", "and", "for", "with", "from", "into", "about", "what", "how"}
    terms = {
        term.lower()
        for term in re.findall(r"[A-Za-z0-9]+", topic)
        if len(term) > 2 and term.lower() not in stop_words
    }
    ranked = []
    for index, section in enumerate(sections, start=1):
        section_terms = {term.lower() for term in re.findall(r"[A-Za-z0-9]+", section)}
        score = len(terms.intersection(section_terms))
        ranked.append((score, index, section))
    matched = [item for item in ranked if item[0] > 0]
    selected = sorted(matched or ranked, key=lambda item: (-item[0], item[1]))[:4]
    results = [
        {
            "source_id": f"SY{index}",
            "title": f"User syllabus section {index}",
            "summary": section[:1600],
            "url": "",
            "source_type": "User syllabus",
            "topic_match": score > 0,
        }
        for score, index, section in selected
    ]
    message = "Matching syllabus sections found." if matched else "No exact topic match; showing the first syllabus sections for context."
    return json.dumps({"results": results, "message": message}, ensure_ascii=False)


@tool
def verify_study_materials(materials_json: str) -> str:
    """Check that generated notes and quiz items cite known sources and have valid answer keys."""
    materials = json.loads(materials_json)
    known_ids = set(materials.get("source_ids", []))
    note_ids = set(re.findall(r"\[(W\d+|SY\d+)\]", materials.get("notes", "")))
    note_check = bool(materials.get("notes", "").strip()) and bool(note_ids) and note_ids.issubset(known_ids)
    quiz_checks = []
    for question in materials.get("questions", []):
        cited_ids = set(question.get("source_ids", []))
        valid = (
            len(question.get("options", [])) >= 3
            and question.get("answer") in question.get("options", [])
            and bool(question.get("explanation", "").strip())
            and bool(cited_ids)
            and cited_ids.issubset(known_ids)
        )
        quiz_checks.append({"question_id": question.get("question_id", "?"), "passed": valid})
    checks = {
        "notes_cite_known_sources": note_check,
        "quiz_items_have_valid_keys_explanations_and_citations": bool(quiz_checks) and all(
            check["passed"] for check in quiz_checks
        ),
        "quiz_item_checks": quiz_checks,
    }
    checks["passed"] = all(
        checks[key]
        for key in (
            "notes_cite_known_sources",
            "quiz_items_have_valid_keys_explanations_and_citations",
        )
    )
    return json.dumps(checks, ensure_ascii=False)


def _ollama_json(context: dict[str, Any], prompt: str) -> dict[str, Any] | None:
    model = context.get("ollama_model")
    if not model or not context.get("ollama_available", False):
        return None
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    request_data = json.dumps(
        {"model": model, "prompt": prompt, "format": "json", "stream": False}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/generate",
        data=request_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
        generated = json.loads(payload["response"])
        context["llm_agents"].append(prompt.splitlines()[0][:80])
        return generated if isinstance(generated, dict) else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, OSError) as error:
        context["ollama_available"] = False
        context["warnings"].append(f"Ollama is configured but unavailable; using evidence-based fallback ({error}).")
        return None


def _source_prompt(sources: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"[{source['source_id']}] {source['title']}: {source['summary'][:1200]}"
        for source in sources
    )


class TopicResearcher:
    profile = PROFILES[0]

    def run(self, subject: str, topic: str, syllabus: str, context: dict[str, Any]) -> None:
        wikipedia_result = json.loads(
            wikipedia_search.invoke({"subject": subject, "topic": topic})
        )
        context["tool_log"].append("wikipedia_search: searched subject and topic")
        sources = wikipedia_result.get("results", [])
        if wikipedia_result.get("error"):
            context["warnings"].append(wikipedia_result["error"])

        syllabus_result = json.loads(
            syllabus_content_search.invoke({"syllabus_text": syllabus, "topic": topic})
        )
        context["tool_log"].append("syllabus_content_search: searched user-provided syllabus")
        sources.extend(syllabus_result.get("results", []))
        if syllabus_result.get("message") and syllabus.strip():
            context["syllabus_search_note"] = syllabus_result["message"]
        if not sources:
            detail = context["warnings"][-1] if context["warnings"] else "No matching research was found."
            raise ValueError(
                f"No research sources are available for this topic. Add syllabus content or retry with internet access. {detail}"
            )

        context["sources"] = sources
        context["handoffs"].append(
            "Topic Researcher -> Study Explainer: passed source extracts, source IDs, and syllabus matches"
        )


class StudyExplainer:
    profile = PROFILES[1]

    def run(self, subject: str, topic: str, context: dict[str, Any]) -> None:
        prompt = (
            "STUDY_NOTES_JSON\nCreate concise, accurate study notes using only the sources below. "
            "Return JSON with overview (string), learning_objectives (array of strings), "
            "study_notes (array of objects with heading, content, source_ids), and "
            "key_terms (array of objects with term, definition, source_ids). Cite only the supplied IDs.\n"
            f"Subject: {subject}\nTopic: {topic}\nSources:\n{_source_prompt(context['sources'])}"
        )
        generated = _ollama_json(context, prompt)
        known_ids = {source["source_id"] for source in context["sources"]}
        if generated:
            context["notes"] = self._format_generated_notes(generated, known_ids, subject, topic)
        if not context.get("notes"):
            context["notes"] = self._fallback_notes(subject, topic, context["sources"])
            context["generation_warnings"].append("Study notes used the evidence-based extractive fallback.")
        context["handoffs"].append(
            "Study Explainer -> Quiz Maker: passed structured notes and cited research findings"
        )

    @staticmethod
    def _format_generated_notes(
        data: dict[str, Any], known_ids: set[str], subject: str, topic: str
    ) -> str | None:
        sections = data.get("study_notes")
        if not isinstance(sections, list) or not sections:
            return None
        lines = [f"## {data.get('overview', f'{topic} in {subject}')}", ""]
        objectives = data.get("learning_objectives", [])
        if objectives:
            lines.extend(["### Learning objectives", ""])
            lines.extend(f"- {objective}" for objective in objectives[:8] if isinstance(objective, str))
            lines.append("")
        lines.extend(["### Core notes", ""])
        for section in sections[:10]:
            if not isinstance(section, dict):
                return None
            source_ids = section.get("source_ids", [])
            if not source_ids or not set(source_ids).issubset(known_ids):
                return None
            lines.extend(
                [
                    f"#### {section.get('heading', 'Key idea')}",
                    str(section.get("content", "")),
                    "Sources: " + " ".join(f"[{source_id}]" for source_id in source_ids),
                    "",
                ]
            )
        terms = data.get("key_terms", [])
        if terms:
            lines.extend(["### Key terms", ""])
            for item in terms[:12]:
                source_ids = item.get("source_ids", [])
                if not source_ids or not set(source_ids).issubset(known_ids):
                    return None
                lines.append(
                    f"- **{item.get('term', 'Term')}**: {item.get('definition', '')} "
                    + " ".join(f"[{source_id}]" for source_id in source_ids)
                )
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _fallback_notes(subject: str, topic: str, sources: list[dict[str, Any]]) -> str:
        lines = [
            f"## {topic} ({subject})",
            "",
            "### Source-backed overview",
            "",
            "These notes summarize retrieved source extracts. Use the linked sources below for fuller context.",
            "",
        ]
        for source in sources:
            lines.extend(
                [
                    f"#### {source['title']}",
                    source["summary"],
                    f"Sources: [{source['source_id']}]",
                    "",
                ]
            )
        lines.extend(
            [
                "### Review prompts",
                "",
                "- Explain the topic in your own words before rereading the notes.",
                "- Identify one key term and connect it to a source above.",
                "- Use the quiz to check recall, then revisit any missed source.",
                "",
            ]
        )
        return "\n".join(lines)


class QuizMaker:
    profile = PROFILES[2]

    def run(self, subject: str, topic: str, quiz_count: int, context: dict[str, Any]) -> None:
        prompt = (
            "STUDY_QUIZ_JSON\nCreate exactly the requested number of four-option MCQs using only "
            "the notes and sources below. Return JSON with questions array; each item must have "
            "question, options (four distinct strings), answer (exactly one option), explanation, "
            "and source_ids (supplied source IDs only). Avoid trick questions.\n"
            f"Requested count: {quiz_count}\nSubject: {subject}\nTopic: {topic}\n"
            f"Notes:\n{context['notes']}\nSources:\n{_source_prompt(context['sources'])}"
        )
        generated = _ollama_json(context, prompt)
        context["questions"] = self._normalize_generated_quiz(
            generated, quiz_count, {source["source_id"] for source in context["sources"]}
        ) if generated else []
        if not context["questions"]:
            context["questions"] = self._fallback_quiz(topic, context["sources"], quiz_count)
            context["generation_warnings"].append("Quiz used the evidence-based extractive fallback.")
        context["handoffs"].append(
            "Quiz Maker -> Fact-Checker: passed question options, answer keys, explanations, and citations"
        )

    @staticmethod
    def _normalize_generated_quiz(
        data: dict[str, Any], count: int, known_ids: set[str]
    ) -> list[dict[str, Any]]:
        questions = data.get("questions")
        if not isinstance(questions, list) or len(questions) < count:
            return []
        normalized = []
        for index, item in enumerate(questions[:count], start=1):
            if not isinstance(item, dict):
                return []
            options = item.get("options")
            source_ids = item.get("source_ids")
            answer = item.get("answer")
            if (
                not isinstance(options, list)
                or len(options) != 4
                or len(set(options)) != 4
                or answer not in options
                or not isinstance(source_ids, list)
                or not source_ids
                or not set(source_ids).issubset(known_ids)
            ):
                return []
            explanation = item.get("explanation", "")
            if not isinstance(explanation, str) or not explanation.strip():
                return []
            normalized.append(
                {
                    "question_id": f"Q{index}",
                    "question": str(item.get("question", "")),
                    "options": [str(option) for option in options],
                    "answer": str(answer),
                    "explanation": explanation,
                    "source_ids": source_ids,
                }
            )
        return normalized

    @staticmethod
    def _fallback_quiz(topic: str, sources: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
        facts = []
        for source in sources:
            sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", source["summary"]) if part.strip()]
            for sentence in sentences:
                facts.append((sentence[:500], source))
        if not facts:
            facts = [(source["summary"][:500], source) for source in sources]

        quiz = []
        for index in range(count):
            fact, source = facts[index % len(facts)]
            distractors = [
                "The supplied source does not discuss this topic.",
                "The source states the opposite without supporting evidence.",
                "The source focuses only on an unrelated subject.",
            ]
            for other_fact, other_source in facts:
                if other_source["source_id"] != source["source_id"] and other_fact != fact:
                    distractors.append(other_fact[:500])
            options = list(dict.fromkeys([fact, *distractors]))[:4]
            while len(options) < 4:
                options.append(f"No supplied source supports the claim: {topic}.")
            # Keep the answer position varied without making correctness depend on option order.
            shift = index % len(options)
            options = options[shift:] + options[:shift]
            quiz.append(
                {
                    "question_id": f"Q{index + 1}",
                    "question": f"Which statement is supported by the research for {topic}?",
                    "options": options,
                    "answer": fact,
                    "explanation": f"This statement appears in {source['title']}: {fact}",
                    "source_ids": [source["source_id"]],
                }
            )
        return quiz


class FactChecker:
    profile = PROFILES[3]

    def run(self, context: dict[str, Any]) -> None:
        payload = {
            "source_ids": [source["source_id"] for source in context["sources"]],
            "notes": context["notes"],
            "questions": context["questions"],
        }
        result = json.loads(verify_study_materials.invoke({"materials_json": json.dumps(payload)}))
        context["tool_log"].append("verify_study_materials: checked citations, keys, options, and explanations")
        context["fact_check"] = result
        context["fact_check_passed"] = result["passed"]
        context["fact_check_scope"] = (
            "Verified that citations exist, answer keys match options, and explanations are present. "
            "This structural check does not independently prove every subject claim."
        )
        if not result["passed"]:
            raise ValueError("Fact-check failed: a note or quiz item has missing or invalid source references.")
        context["handoffs"].append("Fact-Checker -> Study Group: source and quiz structure checks passed")


def run_study_session(
    subject: str,
    topic: str,
    syllabus: str = "",
    quiz_count: int = 5,
) -> dict[str, Any]:
    subject, topic = subject.strip(), topic.strip()
    if not subject or not topic:
        raise ValueError("Enter both a subject and a topic.")
    if not 3 <= quiz_count <= 10:
        raise ValueError("Quiz length must be between 3 and 10 questions.")

    model = os.getenv("OLLAMA_MODEL", "").strip()
    context: dict[str, Any] = {
        "session_id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "subject": subject,
        "topic": topic,
        "sources": [],
        "warnings": [],
        "generation_warnings": [],
        "tool_log": [],
        "handoffs": [],
        "ollama_model": model,
        "ollama_available": bool(model),
        "llm_agents": [],
    }
    TopicResearcher().run(subject, topic, syllabus, context)
    StudyExplainer().run(subject, topic, context)
    QuizMaker().run(subject, topic, quiz_count, context)
    FactChecker().run(context)
    context["generation_mode"] = (
        f"Ollama local model: {model}" if context["llm_agents"] else "Evidence-based extractive fallback"
    )
    return context


def score_quiz(questions: list[dict[str, Any]], answers: dict[str, str]) -> dict[str, Any]:
    unanswered = [question["question_id"] for question in questions if not answers.get(question["question_id"])]
    if unanswered:
        raise ValueError("Answer every question before submitting the quiz.")
    results = [
        {
            "question_id": question["question_id"],
            "question": question["question"],
            "selected": answers[question["question_id"]],
            "answer": question["answer"],
            "correct": answers[question["question_id"]] == question["answer"],
            "explanation": question["explanation"],
            "source_ids": question["source_ids"],
        }
        for question in questions
    ]
    correct = sum(item["correct"] for item in results)
    return {"score": correct, "total": len(questions), "results": results}


def render_report(context: dict[str, Any]) -> str:
    lines = [
        "# Study Group Crew Study Pack",
        "",
        f"**Subject:** {context['subject']}",
        f"**Topic:** {context['topic']}",
        f"**Created:** {context['created_at']}",
        f"**Generation mode:** {context['generation_mode']}",
        "",
        "## Agent Crew",
        "",
    ]
    for profile in PROFILES:
        lines.extend(
            [
                f"### {profile.role}: {profile.name}",
                f"**Goal:** {profile.goal}",
                f"**Backstory:** {profile.backstory}",
                "",
            ]
        )
    lines.extend(["## Study Notes", "", context["notes"], "", "## Practice Quiz", ""])
    attempt = context.get("quiz_attempt")
    if attempt:
        lines.append(f"**Quiz score:** {attempt['score']} / {attempt['total']}")
        lines.append("")
    for question in context["questions"]:
        lines.extend(
            [
                f"### {question['question_id']}. {question['question']}",
                *(f"- {letter}. {option}" for letter, option in zip("ABCD", question["options"])),
                f"**Correct answer:** {question['answer']}",
                f"**Explanation:** {question['explanation']}",
                f"**Sources:** {', '.join(question['source_ids'])}",
                "",
            ]
        )
    lines.extend(
        [
            "## Fact-Checker Results",
            "",
            f"**Status:** {'PASS' if context['fact_check_passed'] else 'REVIEW'}",
            context["fact_check_scope"],
            "",
        ]
    )
    for check_name, passed in context["fact_check"].items():
        if isinstance(passed, bool):
            lines.append(f"- {'PASS' if passed else 'FAIL'}: {check_name.replace('_', ' ')}")
    if attempt:
        lines.extend(["", "## Learner Quiz Results", ""])
        for item in attempt["results"]:
            lines.append(
                f"- {item['question_id']}: {'Correct' if item['correct'] else 'Incorrect'}; "
                f"your answer: {item['selected']}; correct answer: {item['answer']}"
            )
    lines.extend(["", "## LangChain Tool Calls", ""])
    lines.extend(f"- `{entry}`" for entry in context["tool_log"])
    lines.extend(["", "## Task Context Flow", ""])
    lines.extend(f"- {handoff}" for handoff in context["handoffs"])
    lines.extend(["", "## Sources", ""])
    for source in context["sources"]:
        link = f"[{source['title']}]({source['url']})" if source.get("url") else source["title"]
        lines.append(
            f"- **[{source['source_id']}] {link}** ({source['source_type']}): {source['summary']}"
        )
    if context["warnings"] or context["generation_warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in context["warnings"] + context["generation_warnings"])
    lines.extend(
        [
            "",
            "---",
            "Wikipedia extracts and user-provided syllabus text are learning references, not a substitute for course materials.",
            "",
        ]
    )
    return "\n".join(lines)
