"""Tests for call_llm: fixture parsing, markdown stripping, retry logic, schema validation."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.llm import call_llm
from worker.schemas import (
    ExtractedQuestionSet,
    GeneratedQuestionSet,
    RecommendationResult,
    ReviewAssessment,
    ScaffoldedOptionSet,
)

FIXTURES = Path(__file__).parent / "fixtures"

SIMPLE_MESSAGES = [{"role": "user", "content": "generate"}]


def load_fixture(name: str) -> str:
    """Load a fixture JSON file and return its content as a string."""
    return (FIXTURES / name).read_text()


def make_llm_response(content: str):
    """Create a mock litellm response with given content string."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    return mock_response


# ---------------------------------------------------------------------------
# Happy-path: one test per schema
# ---------------------------------------------------------------------------

class TestHappyPathParsing:
    """Each fixture file should parse into its corresponding Pydantic model."""

    @pytest.mark.asyncio
    async def test_parse_question_gen(self):
        content = load_fixture("question_gen_response.json")
        with patch("worker.llm.litellm.acompletion", AsyncMock(return_value=make_llm_response(content))):
            result = await call_llm(SIMPLE_MESSAGES, GeneratedQuestionSet)

        assert isinstance(result, GeneratedQuestionSet)
        assert len(result.questions) == 3
        assert result.questions[0].title == "How do you handle deployment rollbacks?"
        assert result.questions[0].category == "DevOps"
        assert len(result.questions[0].suggested_options) == 4
        assert result.questions[1].suggested_options == []

    @pytest.mark.asyncio
    async def test_parse_extraction(self):
        content = load_fixture("extraction_response.json")
        with patch("worker.llm.litellm.acompletion", AsyncMock(return_value=make_llm_response(content))):
            result = await call_llm(SIMPLE_MESSAGES, ExtractedQuestionSet)

        assert isinstance(result, ExtractedQuestionSet)
        assert len(result.questions) == 2
        assert result.document_summary.startswith("Technical architecture")
        assert result.questions[0].confidence == 0.92
        assert "OAuth 2.0" in result.questions[0].source_passage

    @pytest.mark.asyncio
    async def test_parse_scaffold(self):
        content = load_fixture("scaffold_response.json")
        with patch("worker.llm.litellm.acompletion", AsyncMock(return_value=make_llm_response(content))):
            result = await call_llm(SIMPLE_MESSAGES, ScaffoldedOptionSet)

        assert isinstance(result, ScaffoldedOptionSet)
        assert len(result.options) == 4
        assert result.options[0].display_order == 1
        assert result.options[3].display_order == 4
        assert "microservices" in result.options[0].body

    @pytest.mark.asyncio
    async def test_parse_review(self):
        content = load_fixture("review_response.json")
        with patch("worker.llm.litellm.acompletion", AsyncMock(return_value=make_llm_response(content))):
            result = await call_llm(SIMPLE_MESSAGES, ReviewAssessment)

        assert isinstance(result, ReviewAssessment)
        assert result.verdict == "approved"
        assert result.confidence == 0.82
        assert len(result.strengths) == 3
        assert len(result.weaknesses) == 2
        assert len(result.suggestions) == 2

    @pytest.mark.asyncio
    async def test_parse_recommendation(self):
        content = load_fixture("recommend_response.json")
        with patch("worker.llm.litellm.acompletion", AsyncMock(return_value=make_llm_response(content))):
            result = await call_llm(SIMPLE_MESSAGES, RecommendationResult)

        assert isinstance(result, RecommendationResult)
        assert len(result.respondents) == 2
        assert result.respondents[0].user_id == "user-abc-123"
        assert result.respondents[0].score == 0.95
        assert result.respondents[1].score == 0.73


# ---------------------------------------------------------------------------
# Markdown code-fence stripping
# ---------------------------------------------------------------------------

class TestMarkdownStripping:
    """LLMs sometimes wrap JSON in markdown code fences — call_llm should strip them."""

    @pytest.mark.asyncio
    async def test_json_with_language_tag(self):
        raw = load_fixture("scaffold_response.json")
        wrapped = f"```json\n{raw}\n```"
        with patch("worker.llm.litellm.acompletion", AsyncMock(return_value=make_llm_response(wrapped))):
            result = await call_llm(SIMPLE_MESSAGES, ScaffoldedOptionSet)
        assert isinstance(result, ScaffoldedOptionSet)
        assert len(result.options) == 4

    @pytest.mark.asyncio
    async def test_json_without_language_tag(self):
        raw = load_fixture("scaffold_response.json")
        wrapped = f"```\n{raw}\n```"
        with patch("worker.llm.litellm.acompletion", AsyncMock(return_value=make_llm_response(wrapped))):
            result = await call_llm(SIMPLE_MESSAGES, ScaffoldedOptionSet)
        assert isinstance(result, ScaffoldedOptionSet)
        assert len(result.options) == 4

    @pytest.mark.asyncio
    async def test_clean_json_no_fences(self):
        raw = load_fixture("scaffold_response.json")
        with patch("worker.llm.litellm.acompletion", AsyncMock(return_value=make_llm_response(raw))):
            result = await call_llm(SIMPLE_MESSAGES, ScaffoldedOptionSet)
        assert isinstance(result, ScaffoldedOptionSet)
        assert len(result.options) == 4

    @pytest.mark.asyncio
    async def test_triple_backtick_with_surrounding_whitespace(self):
        raw = load_fixture("review_response.json")
        wrapped = f"\n  ```json\n{raw}\n```  \n"
        with patch("worker.llm.litellm.acompletion", AsyncMock(return_value=make_llm_response(wrapped))):
            result = await call_llm(SIMPLE_MESSAGES, ReviewAssessment)
        assert isinstance(result, ReviewAssessment)
        assert result.verdict == "approved"


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

class TestRetryLogic:
    """call_llm retries on parse failures with exponential backoff."""

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self):
        """First call returns invalid JSON, second returns valid — should succeed."""
        valid_content = load_fixture("scaffold_response.json")
        mock_acompletion = AsyncMock(side_effect=[
            make_llm_response("not json at all"),
            make_llm_response(valid_content),
        ])
        with patch("worker.llm.litellm.acompletion", mock_acompletion), \
             patch("worker.llm.asyncio.sleep", AsyncMock()) as mock_sleep:
            result = await call_llm(SIMPLE_MESSAGES, ScaffoldedOptionSet, max_retries=3)

        assert isinstance(result, ScaffoldedOptionSet)
        assert mock_acompletion.call_count == 2
        mock_sleep.assert_called_once_with(1)  # 2^0 = 1

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_raises(self):
        """All attempts return invalid JSON — should raise RuntimeError."""
        mock_acompletion = AsyncMock(
            return_value=make_llm_response("definitely not json {{{")
        )
        with patch("worker.llm.litellm.acompletion", mock_acompletion), \
             patch("worker.llm.asyncio.sleep", AsyncMock()):
            with pytest.raises(RuntimeError, match="LLM call failed after 3 attempts"):
                await call_llm(SIMPLE_MESSAGES, ScaffoldedOptionSet, max_retries=3)

        assert mock_acompletion.call_count == 3

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self):
        """Verify sleep durations follow 2^attempt pattern."""
        valid_content = load_fixture("scaffold_response.json")
        mock_acompletion = AsyncMock(side_effect=[
            make_llm_response("bad1"),
            make_llm_response("bad2"),
            make_llm_response("bad3"),
            make_llm_response(valid_content),
        ])
        with patch("worker.llm.litellm.acompletion", mock_acompletion), \
             patch("worker.llm.asyncio.sleep", AsyncMock()) as mock_sleep:
            result = await call_llm(SIMPLE_MESSAGES, ScaffoldedOptionSet, max_retries=4)

        assert isinstance(result, ScaffoldedOptionSet)
        assert mock_acompletion.call_count == 4
        # Backoff: 2^0=1, 2^1=2, 2^2=4
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_calls == [1, 2, 4]

    @pytest.mark.asyncio
    async def test_single_retry_max(self):
        """With max_retries=1, no retries occur — fails immediately."""
        mock_acompletion = AsyncMock(
            return_value=make_llm_response("nope")
        )
        with patch("worker.llm.litellm.acompletion", mock_acompletion), \
             patch("worker.llm.asyncio.sleep", AsyncMock()) as mock_sleep:
            with pytest.raises(RuntimeError, match="LLM call failed after 1 attempts"):
                await call_llm(SIMPLE_MESSAGES, ScaffoldedOptionSet, max_retries=1)

        assert mock_acompletion.call_count == 1
        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Schema validation edge cases
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    """Test behavior when response content doesn't match the expected schema."""

    @pytest.mark.asyncio
    async def test_missing_required_field(self):
        """Response missing 'questions' key should fail validation and exhaust retries."""
        bad_json = json.dumps({"not_questions": []})
        mock_acompletion = AsyncMock(return_value=make_llm_response(bad_json))
        with patch("worker.llm.litellm.acompletion", mock_acompletion), \
             patch("worker.llm.asyncio.sleep", AsyncMock()):
            with pytest.raises(RuntimeError, match="LLM call failed after 2 attempts"):
                await call_llm(SIMPLE_MESSAGES, GeneratedQuestionSet, max_retries=2)

    @pytest.mark.asyncio
    async def test_wrong_type_for_field(self):
        """Confidence as string '0.82' should be coerced by Pydantic (lenient parsing)."""
        data = {
            "verdict": "approved",
            "comment": "Good.",
            "strengths": [],
            "weaknesses": [],
            "suggestions": [],
            "confidence": "0.82",
        }
        content = json.dumps(data)
        with patch("worker.llm.litellm.acompletion", AsyncMock(return_value=make_llm_response(content))):
            result = await call_llm(SIMPLE_MESSAGES, ReviewAssessment)
        # Pydantic coerces string "0.82" to float 0.82
        assert result.confidence == 0.82

    @pytest.mark.asyncio
    async def test_extra_fields_ignored(self):
        """Extra fields not in the schema should be silently ignored."""
        data = json.loads(load_fixture("scaffold_response.json"))
        data["extra_field"] = "should be ignored"
        data["options"][0]["unexpected"] = True
        content = json.dumps(data)
        with patch("worker.llm.litellm.acompletion", AsyncMock(return_value=make_llm_response(content))):
            result = await call_llm(SIMPLE_MESSAGES, ScaffoldedOptionSet)
        assert isinstance(result, ScaffoldedOptionSet)
        assert len(result.options) == 4

    @pytest.mark.asyncio
    async def test_empty_string_response_retries(self):
        """Empty string response should fail JSON parsing and trigger retries."""
        valid_content = load_fixture("scaffold_response.json")
        mock_acompletion = AsyncMock(side_effect=[
            make_llm_response(""),
            make_llm_response(valid_content),
        ])
        with patch("worker.llm.litellm.acompletion", mock_acompletion), \
             patch("worker.llm.asyncio.sleep", AsyncMock()):
            result = await call_llm(SIMPLE_MESSAGES, ScaffoldedOptionSet, max_retries=3)
        assert isinstance(result, ScaffoldedOptionSet)
        assert mock_acompletion.call_count == 2

    @pytest.mark.asyncio
    async def test_confidence_out_of_range_fails(self):
        """Confidence > 1.0 should fail Pydantic validation and exhaust retries."""
        data = {
            "verdict": "approved",
            "comment": "Great.",
            "strengths": [],
            "weaknesses": [],
            "suggestions": [],
            "confidence": 1.5,
        }
        content = json.dumps(data)
        mock_acompletion = AsyncMock(return_value=make_llm_response(content))
        with patch("worker.llm.litellm.acompletion", mock_acompletion), \
             patch("worker.llm.asyncio.sleep", AsyncMock()):
            with pytest.raises(RuntimeError, match="LLM call failed after 2 attempts"):
                await call_llm(SIMPLE_MESSAGES, ReviewAssessment, max_retries=2)

    @pytest.mark.asyncio
    async def test_invalid_verdict_literal_fails(self):
        """Verdict not in Literal['approved', 'changes_requested'] should fail."""
        data = {
            "verdict": "maybe",
            "comment": "Unsure.",
            "strengths": [],
            "weaknesses": [],
            "suggestions": [],
            "confidence": 0.5,
        }
        content = json.dumps(data)
        mock_acompletion = AsyncMock(return_value=make_llm_response(content))
        with patch("worker.llm.litellm.acompletion", mock_acompletion), \
             patch("worker.llm.asyncio.sleep", AsyncMock()):
            with pytest.raises(RuntimeError, match="LLM call failed after 2 attempts"):
                await call_llm(SIMPLE_MESSAGES, ReviewAssessment, max_retries=2)


# ---------------------------------------------------------------------------
# Message enrichment
# ---------------------------------------------------------------------------

class TestMessageEnrichment:
    """call_llm appends a JSON schema instruction to system messages."""

    @pytest.mark.asyncio
    async def test_schema_appended_to_existing_system_message(self):
        """When a system message exists, schema instruction is appended to it."""
        content = load_fixture("scaffold_response.json")
        mock_acompletion = AsyncMock(return_value=make_llm_response(content))
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "generate"},
        ]
        with patch("worker.llm.litellm.acompletion", mock_acompletion):
            await call_llm(messages, ScaffoldedOptionSet)

        sent_messages = mock_acompletion.call_args.kwargs["messages"]
        assert len(sent_messages) == 2
        assert sent_messages[0]["role"] == "system"
        assert "You are helpful." in sent_messages[0]["content"]
        assert "JSON" in sent_messages[0]["content"]

    @pytest.mark.asyncio
    async def test_schema_added_as_new_system_message_when_missing(self):
        """When no system message exists, one is created with the schema."""
        content = load_fixture("scaffold_response.json")
        mock_acompletion = AsyncMock(return_value=make_llm_response(content))
        messages = [{"role": "user", "content": "generate"}]
        with patch("worker.llm.litellm.acompletion", mock_acompletion):
            await call_llm(messages, ScaffoldedOptionSet)

        sent_messages = mock_acompletion.call_args.kwargs["messages"]
        assert sent_messages[0]["role"] == "system"
        assert "JSON" in sent_messages[0]["content"]
        assert sent_messages[1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_schema_appended_only_to_first_system_message(self):
        """Only the first system message gets the schema appended."""
        content = load_fixture("scaffold_response.json")
        mock_acompletion = AsyncMock(return_value=make_llm_response(content))
        messages = [
            {"role": "system", "content": "System A."},
            {"role": "system", "content": "System B."},
            {"role": "user", "content": "go"},
        ]
        with patch("worker.llm.litellm.acompletion", mock_acompletion):
            await call_llm(messages, ScaffoldedOptionSet)

        sent_messages = mock_acompletion.call_args.kwargs["messages"]
        assert "JSON" in sent_messages[0]["content"]
        assert "JSON" not in sent_messages[1]["content"]
        assert sent_messages[1]["content"] == "System B."
