from __future__ import annotations

import unittest
from unittest.mock import Mock

import requests

from src.llm.ollama_client import OllamaClient


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class _CapturingOllamaClient(OllamaClient):
    def __init__(self) -> None:
        super().__init__(model="test-model", timeout_seconds=1)
        self.payloads: list[dict] = []

    def _post_generate(self, payload: dict):  # noqa: ANN001
        self.payloads.append(payload)
        return _FakeResponse({"response": '{"tasks": []}'})


class _MemoryRetryOllamaClient(OllamaClient):
    def __init__(self) -> None:
        super().__init__(model="test-model", timeout_seconds=1)
        self.payloads: list[dict] = []

    def _post_generate(self, payload: dict):  # noqa: ANN001
        self.payloads.append(payload)
        if payload["options"]["num_ctx"] > 2048:
            response = Mock()
            response.status_code = 500
            response.text = '{"error":"model requires more system memory (6.0 GiB) than is available (3.9 GiB)"}'
            raise requests.exceptions.HTTPError("500 Server Error", response=response)
        return _FakeResponse({"response": '{"tasks": []}'})


class _ConnectionRetryOllamaClient(OllamaClient):
    def __init__(self) -> None:
        super().__init__(model="test-model", timeout_seconds=1)
        self.payloads: list[dict] = []

    def _post_generate(self, payload: dict):  # noqa: ANN001
        self.payloads.append(payload)
        if payload["options"]["num_ctx"] > 2048:
            raise requests.exceptions.ConnectionError("connection reset")
        return _FakeResponse({"response": '{"tasks": []}'})


class _TimeoutOllamaClient(OllamaClient):
    def __init__(self) -> None:
        super().__init__(model="test-model", timeout_seconds=1)
        self.payloads: list[dict] = []

    def _post_generate(self, payload: dict):  # noqa: ANN001
        self.payloads.append(payload)
        raise requests.exceptions.ReadTimeout("model took too long")


class _SingleTaskThenTaskListClient(OllamaClient):
    def __init__(self) -> None:
        super().__init__(model="test-model", timeout_seconds=1)
        self.payloads: list[dict] = []

    def _post_generate(self, payload: dict):  # noqa: ANN001
        self.payloads.append(payload)
        if payload.get("format") == "json":
            return _FakeResponse(
                {
                    "response": (
                        '{"id":"T001","title":"Implement login","description":"Users can login",'
                        '"req_type":"FR","complexity":2,"dependencies":[],"source":"line 1"}'
                    )
                }
            )
        return _FakeResponse(
            {
                "response": (
                    'Here is the JSON:\\n'
                    '{"tasks":['
                    '{"id":"T001","title":"Implement login","description":"Users can login","req_type":"FR","complexity":2,"dependencies":[],"source":"line 1"},'
                    '{"id":"T002","title":"Implement logout","description":"Users can logout","req_type":"FR","complexity":2,"dependencies":[],"source":"line 2"}'
                    ']}'
                )
            }
        )


class _RepeatedTaskFieldsClient(OllamaClient):
    def __init__(self) -> None:
        super().__init__(model="test-model", timeout_seconds=1)

    def _post_generate(self, payload: dict):  # noqa: ANN001
        return _FakeResponse(
            {
                "response": (
                    '{"id":"T001","title":"Implement login","description":"Users can login","req_type":"FR","complexity":2,"dependencies":[],"source":"line 1",'
                    '"id":"T002","title":"Implement logout","description":"Users can logout","req_type":"FR","complexity":2,"dependencies":[],"source":"line 2"}'
                )
            }
        )


class OllamaClientBudgetTests(unittest.TestCase):
    def test_token_budget_scales_with_document(self) -> None:
        client = _CapturingOllamaClient()
        client.num_ctx = 9000

        client.generate_json("x" * 1000, output_schema={"type": "object"})
        short_budget = client.payloads[-1]["options"]["num_predict"]

        client.generate_json("x" * 16000, output_schema={"type": "object"})
        long_budget = client.payloads[-1]["options"]["num_predict"]

        self.assertGreaterEqual(short_budget, 4096)
        self.assertGreaterEqual(long_budget, 4096)
        self.assertLess(long_budget, short_budget)
        self.assertLessEqual(short_budget, 8192)
        self.assertLessEqual(long_budget, 8192)

    def test_memory_pressure_retries_with_smaller_context(self) -> None:
        client = _MemoryRetryOllamaClient()
        client.num_ctx = 4096

        result = client.generate_json("x" * 2000, output_schema={"type": "object"})

        self.assertEqual(result, {"tasks": []})
        attempted_contexts = [payload["options"]["num_ctx"] for payload in client.payloads]
        self.assertEqual(attempted_contexts[0], 4096)
        self.assertIn(2048, attempted_contexts)
        self.assertLess(attempted_contexts[-1], attempted_contexts[0])

    def test_connection_reset_retries_with_smaller_context(self) -> None:
        client = _ConnectionRetryOllamaClient()
        client.num_ctx = 4096

        result = client.generate_json("x" * 2000, output_schema={"type": "object"})

        self.assertEqual(result, {"tasks": []})
        attempted_contexts = [payload["options"]["num_ctx"] for payload in client.payloads]
        self.assertEqual(attempted_contexts[0], 4096)
        self.assertIn(2048, attempted_contexts)

    def test_timeout_fails_fast_without_context_retries(self) -> None:
        client = _TimeoutOllamaClient()
        client.num_ctx = 4096

        with self.assertRaises(requests.exceptions.ReadTimeout):
            client.generate_json("x" * 2000, output_schema={"type": "object"})

        self.assertEqual(len(client.payloads), 1)

    def test_large_prompt_context_candidates_do_not_expand_context(self) -> None:
        client = _CapturingOllamaClient()
        client.num_ctx = 4096

        candidates = client._context_candidates_for_prompt("x" * 20000)

        self.assertEqual(candidates[0], 4096)
        self.assertTrue(all(candidate <= 4096 for candidate in candidates))
        self.assertIn(2048, candidates)

    def test_single_task_json_candidate_falls_through_to_nonformat_tasklist(self) -> None:
        client = _SingleTaskThenTaskListClient()

        result = client.generate_json(
            "x" * 2000,
            output_schema={
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                    }
                },
            },
        )

        self.assertEqual(len(result["tasks"]), 2)
        attempted_formats = [payload.get("format") for payload in client.payloads[:2]]
        self.assertEqual(attempted_formats, ["json", None])

    def test_extract_first_json_object_prefers_largest_tasklist_candidate(self) -> None:
        text = (
            '{"tasks":[{"id":"T001"}]}'
            '\n'
            '{"tasks":[{"id":"T001"},{"id":"T002"}]}'
        )

        result = OllamaClient._extract_first_json_object(text)

        self.assertEqual(len(result["tasks"]), 2)

    def test_repeated_task_fields_object_is_salvaged_into_tasklist(self) -> None:
        client = _RepeatedTaskFieldsClient()

        result = client.generate_json(
            "x" * 2000,
            output_schema={
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                    }
                },
            },
        )

        self.assertEqual([task["id"] for task in result["tasks"]], ["T001", "T002"])


if __name__ == "__main__":
    unittest.main()
