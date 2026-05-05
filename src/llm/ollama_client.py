from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests
from requests import Response


class OllamaClient:
    """Ollama HTTP client optimized for local planning models."""

    def __init__(
        self,
        model: str = "ai-project-manager-planner",
        base_url: str = "http://localhost:11434",
        timeout_seconds: int | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        env_timeout = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300"))
        self.timeout_seconds = timeout_seconds or env_timeout
        self.num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
        self.min_num_ctx = int(os.getenv("OLLAMA_MIN_NUM_CTX", "1024"))
        self.min_num_predict = int(os.getenv("OLLAMA_MIN_NUM_PREDICT", "4096"))
        self.max_num_predict = int(os.getenv("OLLAMA_MAX_NUM_PREDICT", "8192"))
        self.last_latency_ms: int = 0

    def generate_json(
        self,
        prompt: str,
        output_schema: dict[str, Any] | None = None,
        strict_json_only: bool = False,
    ) -> dict[str, Any]:
        format_candidates: list[Any] = []
        if output_schema is not None and os.getenv("OLLAMA_USE_JSON_SCHEMA") == "1":
            format_candidates.append(output_schema)
        format_candidates.extend(["json", None])

        last_error: Exception | None = None
        for num_ctx in self._context_candidates_for_prompt(prompt):
            num_predict = self._num_predict_for_prompt(prompt, num_ctx)
            base_payload: dict[str, Any] = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0,
                    "top_p": 0.9,
                    "repeat_penalty": 1.1,
                    "num_ctx": num_ctx,
                    "num_predict": num_predict,
                },
            }

            retry_with_smaller_context = False
            for candidate in format_candidates:
                payload = dict(base_payload)
                if candidate is not None:
                    payload["format"] = candidate

                try:
                    response = self._post_generate(payload)
                    raw_text = response.json().get("response", "")
                    cleaned = self._clean_model_output(raw_text)

                    parsed = self._extract_json_with_schema_awareness(
                        cleaned,
                        output_schema=output_schema,
                        strict_json_only=strict_json_only,
                    )
                    return parsed

                except requests.exceptions.HTTPError as exc:
                    last_error = exc
                    if self._is_memory_pressure_error(exc):
                        retry_with_smaller_context = True
                        break
                    status_code = exc.response.status_code if exc.response is not None else 0
                    if candidate is not None and status_code in {400, 422, 500}:
                        continue
                    raise
                except requests.exceptions.Timeout as exc:
                    last_error = exc
                    raise
                except requests.exceptions.RequestException as exc:
                    last_error = exc
                    retry_with_smaller_context = True
                    break
                except ValueError as exc:
                    last_error = exc
                    continue

            if retry_with_smaller_context:
                continue

        if last_error is not None:
            raise last_error
        raise ValueError("Failed to generate JSON from Ollama response")

    # ------------------------------------------------------------------ #
    # HTTP                                                               #
    # ------------------------------------------------------------------ #

    def _num_predict_for_prompt(self, prompt: str, num_ctx: int | None = None) -> int:
        effective_num_ctx = num_ctx or self.num_ctx
        estimated_input_tokens = max(len(prompt) // 4, 1)
        available_completion_tokens = max(effective_num_ctx - estimated_input_tokens - 256, 256)

        if available_completion_tokens >= self.min_num_predict:
            return min(available_completion_tokens, self.max_num_predict)
        return available_completion_tokens

    def _context_candidates_for_prompt(self, prompt: str) -> list[int]:
        candidates = [self.num_ctx, 3072, 2048, 1536, 1024, self.min_num_ctx]

        filtered: list[int] = []
        for candidate in candidates:
            if candidate < self.min_num_ctx:
                continue
            if candidate > self.num_ctx:
                continue
            if candidate not in filtered:
                filtered.append(candidate)

        if not filtered:
            filtered.append(max(self.min_num_ctx, self.num_ctx))
        return filtered

    @staticmethod
    def _is_memory_pressure_error(exc: requests.exceptions.HTTPError) -> bool:
        if exc.response is None:
            return False
        return (
            exc.response.status_code == 500
            and (
                "requires more system memory" in exc.response.text.lower()
                or "memory layout cannot be allocated" in exc.response.text.lower()
            )
        )

    def _post_generate(self, payload: dict[str, Any]) -> Response:
        start = time.perf_counter()
        response = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=self.timeout_seconds,
        )
        end = time.perf_counter()
        self.last_latency_ms = round((end - start) * 1000)
        response.raise_for_status()
        return response

    # ------------------------------------------------------------------ #
    # Output cleaning                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _clean_model_output(text: str) -> str:
        """
        Strip Qwen thinking blocks and common formatting artifacts.
        """
        cleaned = re.sub(
            r"<think>.*?</think>",
            "",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

        cleaned = re.sub(
            r"```(?:json)?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = cleaned.replace("```", "")

        cleaned = re.sub(
            r"^(?:here(?:'s| is)(?: the)?(?: (?:json|plan|output|result|response))?[:\s]*)+",
            "",
            cleaned,
            flags=re.IGNORECASE | re.MULTILINE,
        )

        return cleaned.strip()

    # ------------------------------------------------------------------ #
    # JSON extraction                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_first_json_object(text: str) -> dict[str, Any]:
        decoder = json.JSONDecoder()
        candidates: list[dict[str, Any]] = []

        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(text[index:])
                if isinstance(obj, dict):
                    candidates.append(obj)
            except json.JSONDecodeError:
                continue

        tasklist_candidates = [
            candidate for candidate in candidates
            if isinstance(candidate.get("tasks"), list)
        ]
        if tasklist_candidates:
            return max(
                tasklist_candidates,
                key=lambda candidate: len(candidate.get("tasks", [])),
            )

        if candidates:
            return candidates[0]

        preview = text[:300].replace("\n", "\\n")
        raise ValueError(
            "LLM response did not contain a valid JSON object. "
            f"Response preview: {preview}"
        )

    @staticmethod
    def _extract_strict_json_object(text: str) -> dict[str, Any]:
        decoder = json.JSONDecoder()
        try:
            obj, end_idx = decoder.raw_decode(text.strip())
        except json.JSONDecodeError as exc:
            preview = text[:300].replace("\n", "\\n")
            raise ValueError(
                f"LLM response is not strict JSON. Preview: {preview}"
            ) from exc

        trailing = text.strip()[end_idx:].strip()
        if trailing:
            raise ValueError(f"LLM response has trailing text after JSON: {trailing[:100]!r}")
        if not isinstance(obj, dict):
            raise ValueError("LLM strict JSON response is not an object")
        return obj

    @classmethod
    def _extract_json_with_schema_awareness(
        cls,
        text: str,
        *,
        output_schema: dict[str, Any] | None,
        strict_json_only: bool,
    ) -> dict[str, Any]:
        expects_tasks = cls._expects_top_level_tasks(output_schema)
        try:
            parsed = (
                cls._extract_strict_json_object(text)
                if strict_json_only
                else cls._extract_first_json_object(text)
            )
        except ValueError:
            if expects_tasks:
                salvaged = cls._salvage_repeated_task_object(text)
                if salvaged is not None:
                    return salvaged
            raise

        if not expects_tasks:
            return parsed
        if isinstance(parsed.get("tasks"), list):
            return parsed

        salvaged = cls._salvage_repeated_task_object(text)
        if salvaged is not None:
            return salvaged

        if cls._looks_like_single_task_object(parsed):
            raise ValueError(
                "LLM response returned a single task object where a top-level tasks array was expected."
            )
        return parsed

    @staticmethod
    def _expects_top_level_tasks(output_schema: dict[str, Any] | None) -> bool:
        if not isinstance(output_schema, dict):
            return False
        properties = output_schema.get("properties")
        if not isinstance(properties, dict):
            return False
        tasks_schema = properties.get("tasks")
        return isinstance(tasks_schema, dict) and tasks_schema.get("type") == "array"

    @staticmethod
    def _looks_like_single_task_object(obj: dict[str, Any]) -> bool:
        if not isinstance(obj, dict) or "tasks" in obj:
            return False
        taskish_keys = {
            "id",
            "title",
            "description",
            "req_type",
            "complexity",
            "dependencies",
            "source",
        }
        overlap = taskish_keys & set(obj.keys())
        return len(overlap) >= 3 and "id" in overlap and "title" in overlap

    @staticmethod
    def _salvage_repeated_task_object(text: str) -> dict[str, Any] | None:
        id_matches = list(re.finditer(r'"id"\s*:\s*"(?P<id>T\d{3})"', text))
        if len(id_matches) < 2:
            return None

        tasks: list[dict[str, Any]] = []
        for index, match in enumerate(id_matches):
            start = match.start()
            end = id_matches[index + 1].start() if index + 1 < len(id_matches) else len(text)
            chunk = text[start:end]

            def capture(pattern: str) -> str | None:
                found = re.search(pattern, chunk, flags=re.IGNORECASE | re.DOTALL)
                return found.group(1).strip() if found else None

            task_id = capture(r'"id"\s*:\s*"([^"]+)"')
            title = capture(r'"title"\s*:\s*"([^"]+)"')
            description = capture(r'"description"\s*:\s*"([^"]+)"')
            req_type = capture(r'"req_type"\s*:\s*"([^"]+)"')
            source = capture(r'"source"\s*:\s*"([^"]+)"')
            complexity_text = (
                capture(r'"complexity"\s*:\s*(\d+)')
                or capture(r'"calculated_complexity"\s*:\s*(\d+)')
            )
            dependencies_text = capture(r'"dependencies"\s*:\s*(\[[^\]]*\])')

            if not all([task_id, title, description, req_type]):
                continue

            dependencies: list[str] = []
            if dependencies_text:
                try:
                    loaded_dependencies = json.loads(dependencies_text)
                    if isinstance(loaded_dependencies, list):
                        dependencies = [
                            dep for dep in loaded_dependencies if isinstance(dep, str)
                        ]
                except json.JSONDecodeError:
                    dependencies = []

            task_payload: dict[str, Any] = {
                "id": task_id,
                "title": title,
                "description": description,
                "req_type": req_type,
                "complexity": int(complexity_text) if complexity_text is not None else 2,
                "dependencies": dependencies,
                "source": source or "",
            }
            tasks.append(task_payload)

        return {"tasks": tasks} if len(tasks) >= 2 else None
