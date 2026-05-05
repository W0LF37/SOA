from __future__ import annotations

import re

from src.agents.planner import RequirementItem


class TemplateValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors) if errors else "Template validation failed.")


class TemplateParser:
    _BLOCK_HEADER_RE = re.compile(r"^\[(REQ-(\d+))\]\s*$", re.IGNORECASE)
    _FIELD_RE = re.compile(r"^\s*([A-Za-z]+)\s*:\s*(.*)\s*$")
    _ALLOWED_FIELDS = {"type", "description", "actor", "priority", "notes"}
    _VALID_TYPES = {"functional", "non-functional"}
    _VALID_PRIORITIES = {"high", "medium", "low"}

    def parse(self, text: str) -> list[RequirementItem]:
        blocks = self._split_blocks(text)
        errors: list[str] = []
        parsed_blocks: list[dict[str, str]] = []

        for source, block_lines in blocks:
            fields = self._parse_fields(block_lines)
            description = fields.get("description", "").strip()
            if not description:
                continue

            type_value = fields.get("type", "")
            if type_value and type_value.casefold() not in self._VALID_TYPES:
                errors.append(
                    f"{source}: Type must be Functional or Non-Functional, got: '{type_value}'"
                )

            priority_value = fields.get("priority", "")
            if priority_value and priority_value.casefold() not in self._VALID_PRIORITIES:
                errors.append(
                    f"{source}: Priority must be High, Medium, or Low, got: '{priority_value}'"
                )

            if len(description.split()) < 5:
                errors.append(f"{source}: Description is too short (minimum 5 words)")

            parsed_blocks.append(
                {
                    "source": source,
                    "description": description,
                    "actor": fields.get("actor", "").strip(),
                    "notes": fields.get("notes", "").strip(),
                }
            )

        if not parsed_blocks:
            errors.append("At least one block with a valid Description must exist.")

        if errors:
            raise TemplateValidationError(errors)

        items: list[RequirementItem] = []
        for index, block in enumerate(parsed_blocks, start=1):
            text_value = block["description"]
            if block["actor"]:
                text_value = f"Actor: {block['actor']} — {text_value}"
            if block["notes"]:
                text_value = f"{text_value} Notes: {block['notes']}"
            items.append(
                RequirementItem(
                    line_no=index,
                    source=block["source"],
                    text=text_value,
                    sources=(block["source"],),
                )
            )
        return items

    @classmethod
    def _split_blocks(cls, text: str) -> list[tuple[str, list[str]]]:
        blocks: list[tuple[str, list[str]]] = []
        current_source: str | None = None
        current_lines: list[str] = []

        for raw_line in text.splitlines():
            match = cls._BLOCK_HEADER_RE.match(raw_line.strip())
            if match:
                if current_source is not None:
                    blocks.append((current_source, current_lines))
                current_source = match.group(1).upper()
                current_lines = []
                continue
            if current_source is not None:
                current_lines.append(raw_line)

        if current_source is not None:
            blocks.append((current_source, current_lines))

        return blocks

    @classmethod
    def _parse_fields(cls, block_lines: list[str]) -> dict[str, str]:
        fields: dict[str, str] = {}
        for raw_line in block_lines:
            match = cls._FIELD_RE.match(raw_line)
            if not match:
                continue
            key = match.group(1).strip().casefold()
            if key not in cls._ALLOWED_FIELDS:
                continue
            fields[key] = match.group(2).strip()
        return fields
