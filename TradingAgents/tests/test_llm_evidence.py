"""LLM evidence preserves messages/tool calls/schema outputs without live replay."""
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from tradingagents.agents.structured import invoke_structured
from tradingagents.evidence import EvidenceStore
from tradingagents.evidence.capture import EvidenceCaptureError
from tradingagents.evidence.llm import LLMReplayError, RecordedModel, replay_llm
from tradingagents.runs.manifest import analysis_run


class Answer(BaseModel):
    value: int


def config(tmp_path, **kwargs):
    return {"results_dir": str(tmp_path), "evidence_llm_responses": True, **kwargs}


def test_message_and_tool_calls_roundtrip(tmp_path):
    answer = AIMessage(content="result", tool_calls=[{"id": "one", "name": "lookup", "args": {"ticker": "AAPL"}}])
    delegate = Mock()
    delegate.invoke.return_value = answer
    model = RecordedModel(delegate, {"model": "fixture", "temperature": 0})
    prompt = [HumanMessage(content="query")]
    with analysis_run(config(tmp_path), "AAPL", "2026-01-05", []) as run:
        assert model.invoke(prompt) == answer
    store = EvidenceStore(tmp_path / "evidence")
    ids = [r["evidence_id"] for r in run["llm_evidence"]]
    delegate.invoke.side_effect = AssertionError("no provider call")
    with replay_llm(store, ids):
        assert model.invoke(prompt) == answer
        with pytest.raises(LLMReplayError):
            model.invoke([HumanMessage(content="changed")])
    delegate.invoke.assert_called_once()


def test_structured_result_roundtrip_without_delegate(tmp_path):
    delegate = Mock()
    delegate.with_structured_output.return_value.invoke.return_value = Answer(value=42)
    model = RecordedModel(delegate, "fixture").with_structured_output(Answer)
    with analysis_run(config(tmp_path), "AAPL", "2026-01-05", []) as run:
        model.invoke("question")
    replay = RecordedModel(None, "fixture").with_structured_output(Answer)
    with replay_llm(EvidenceStore(tmp_path / "evidence"), [run["llm_evidence"][0]["evidence_id"]]):
        assert replay.invoke("question") == Answer(value=42)


def test_storage_failure_not_swallowed_by_structured_fallback(tmp_path, monkeypatch):
    delegate = Mock()
    delegate.invoke.return_value = Answer(value=42)
    monkeypatch.setattr(EvidenceStore, "put", Mock(side_effect=OSError("disk")))
    with pytest.raises(EvidenceCaptureError), analysis_run(config(tmp_path), "AAPL", "2026-01-05", []) as run:
        invoke_structured(RecordedModel(delegate, "fixture"), "question", "test")
    assert run["status"] == "failed"


def test_disabled_capture_and_context_reset(tmp_path):
    delegate = Mock()
    delegate.invoke.return_value = AIMessage(content="ok")
    model = RecordedModel(delegate, "fixture")
    with analysis_run(config(tmp_path, evidence_llm_responses=False), "AAPL", "2026-01-05", []) as run:
        model.invoke("question")
    model.invoke("outside")
    assert run["llm_evidence"] == []
    assert not (tmp_path / "evidence").exists()


def test_conflicting_responses_require_selection(tmp_path):
    delegate = Mock()
    delegate.invoke.side_effect = [AIMessage(content="first"), AIMessage(content="second")]
    model = RecordedModel(delegate, "fixture")
    with analysis_run(config(tmp_path), "AAPL", "2026-01-05", []) as run:
        model.invoke("same")
        model.invoke("same")
    ids = [r["evidence_id"] for r in run["llm_evidence"]]
    with pytest.raises(LLMReplayError, match="conflicting"), replay_llm(EvidenceStore(tmp_path / "evidence"), ids):
        pass


def test_model_identity_changes_invalidate_replay(tmp_path):
    delegate = Mock()
    delegate.invoke.return_value = AIMessage(content="ok")
    with analysis_run(config(tmp_path), "AAPL", "2026-01-05", []) as run:
        RecordedModel(delegate, "model1").invoke("question")
    with replay_llm(EvidenceStore(tmp_path / "evidence"), [run["llm_evidence"][0]["evidence_id"]]), pytest.raises(LLMReplayError):
        RecordedModel(None, "model2").invoke("question")


def test_tool_schema_is_part_of_request_identity(tmp_path):
    delegate = Mock()
    delegate.bind_tools.return_value.invoke.return_value = AIMessage(content="ok")
    schema = {"type": "function", "function": {"name": "lookup", "description": "lookup", "parameters": {"type": "object", "properties": {}}}}
    with analysis_run(config(tmp_path), "AAPL", "2026-01-05", []) as run:
        RecordedModel(delegate, "fixture").bind_tools([schema]).invoke("question")
    with replay_llm(EvidenceStore(tmp_path / "evidence"), [run["llm_evidence"][0]["evidence_id"]]):
        assert RecordedModel(None, "fixture").bind_tools([schema]).invoke("question").content == "ok"
        with pytest.raises(LLMReplayError):
            RecordedModel(None, "fixture").invoke("question")


def test_scheduler_objects_are_excluded_but_model_overrides_are_matched(tmp_path):
    delegate = Mock()
    delegate.invoke.return_value = AIMessage(content="ok")
    model = RecordedModel(delegate, "fixture")
    with analysis_run(config(tmp_path), "AAPL", "2026-01-05", []) as run:
        model.invoke("question", config={"configurable": {"__pregel_runtime": object(), "temperature": .1}})
    with replay_llm(EvidenceStore(tmp_path / "evidence"), [run["llm_evidence"][0]["evidence_id"]]):
        assert model.invoke("question", config={"configurable": {"temperature": .1}}).content == "ok"
        with pytest.raises(LLMReplayError):
            model.invoke("question", config={"configurable": {"temperature": .9}})


def test_unsupported_request_cannot_trigger_provider_fallback(tmp_path):
    delegate = Mock()
    with pytest.raises(EvidenceCaptureError), analysis_run(config(tmp_path), "AAPL", "2026-01-05", []):
        invoke_structured(RecordedModel(delegate, "fixture"), object(), "test")
    delegate.invoke.assert_not_called()


def test_prompt_message_ids_do_not_mask_content_changes(tmp_path):
    from langchain_core.messages import HumanMessage
    from langchain_core.prompt_values import ChatPromptValue

    delegate = Mock()
    delegate.invoke.return_value = AIMessage(content="ok")
    with analysis_run(config(tmp_path), "AAPL", "2026-01-05", []) as run:
        RecordedModel(delegate, "fixture").invoke(
            ChatPromptValue(messages=[HumanMessage("question", id="original")]))
    with replay_llm(EvidenceStore(tmp_path / "evidence"), [run["llm_evidence"][0]["evidence_id"]]):
        model = RecordedModel(None, "fixture")
        assert model.invoke(ChatPromptValue(messages=[HumanMessage("question", id="new")])).content == "ok"
        with pytest.raises(LLMReplayError):
            model.invoke(ChatPromptValue(messages=[HumanMessage("different", id="new")]))


def test_message_content_is_not_interpreted_as_archive_wrappers(tmp_path):
    from langchain_core.messages import HumanMessage

    delegate = Mock()
    delegate.invoke.return_value = AIMessage(content="ok")
    prompt = [HumanMessage(content=[{"kind": "message"}])]
    with analysis_run(config(tmp_path), "AAPL", "2026-01-05", []) as run:
        RecordedModel(delegate, "fixture").invoke(prompt)
    with replay_llm(EvidenceStore(tmp_path / "evidence"), [run["llm_evidence"][0]["evidence_id"]]):
        assert RecordedModel(None, "fixture").invoke(prompt).content == "ok"


def test_failed_invocation_records_type_without_exception_message(tmp_path):
    from tradingagents.evidence.llm import RecordedInvocationError

    delegate = Mock()
    delegate.invoke.side_effect = ValueError("secret-provider-response")
    with analysis_run(config(tmp_path), "AAPL", "2026-01-05", []) as run, pytest.raises(ValueError):
        RecordedModel(delegate, "fixture").invoke("question")
    ids = [run["llm_evidence"][0]["evidence_id"]]
    store = EvidenceStore(tmp_path / "evidence")
    assert store.get(ids[0])["payload"]["response"] == {"kind": "error", "data": "ValueError"}
    with replay_llm(store, ids), pytest.raises(RecordedInvocationError, match="ValueError"):
        RecordedModel(None, "fixture").invoke("question")
