from __future__ import annotations

import re

from src.agents.planner import RequirementItem


class BriefValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


class BriefParser:
    KNOWN_SECTIONS = (
        "Project Title",
        "Project Overview",
        "Problem Statement",
        "Proposed Solution",
        "Target Users",
        "Actors",
        "Main Features",
        "Functional Requirements",
        "Non-Functional Requirements",
        "Expected Benefits",
        "Constraints or Special Notes",
    )

    _SECTION_RE = re.compile(
        r"^(%s)\s*:\s*$" % "|".join(re.escape(section) for section in KNOWN_SECTIONS),
        re.IGNORECASE,
    )
    _BULLET_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$")
    _SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+")
    _NFR_KEYWORDS = frozenset(
        {
            "fast",
            "reliable",
            "secure",
            "security",
            "scalable",
            "available",
            "availability",
            "performance",
            "maintainable",
            "usable",
            "accessible",
            "responsive",
            "efficient",
            "stable",
            "safe",
            "support",
            "respond",
            "response",
            "latency",
            "language",
            "multilingual",
            "compatible",
            "concurrent",
            "downtime",
            "uptime",
            "backup",
            "recovery",
            "audit",
            "compliance",
            "encrypt",
            "encryption",
            "offline",
            "pci",
            "gdpr",
            "hipaa",
            "iso",
            "privacy",
            "compliant",
            "observable",
            "biometric",
            "authentication",
            "authorization",
            "tls",
            "ssl",
            "reliability",
            "scalability",
            "throughput",
            "bandwidth",
            "accessible",
            "accessibility",
            "retention",
            "restore",
            "resilience",
            "biometrics",
            "authentication",
            "authorization",
            "idempotent",
            "offline",
            "sync",
            "backup",
            "audit",
            "traceability",
            "tracing",
            "observability",
            "monitoring",
            "availability",
            "mobile",
            "responsive",
            "multitenant",
            "tenant",
            "whitelabel",
            "localization",
            "localisation",
            "sandbox",
            "sla",
            "slo",
            "wcag",
            "a11y",
            "soc2",
            "fedramp",
            "nist",
            "rto",
            "rpo",
            "aml",
            "kyc",
            "tokenized",
            "tokenization",
            "cardholder",
        }
    )
    _NFR_PATTERNS = (
        re.compile(r"\bmobile[\-\s]?(?:first|friendly)\b", re.IGNORECASE),
        re.compile(r"\bpeak[\-\s]?load\b", re.IGNORECASE),
        re.compile(r"\b(?:2fa|mfa|multi[\-\s]?factor|two[\-\s]?factor)\b", re.IGNORECASE),
        re.compile(r"\baudit[\-\s]?(?:log|logs|trail|trails)\b", re.IGNORECASE),
        re.compile(r"\b(?:p95|p99|sla|slo|rto|rpo)\b", re.IGNORECASE),
        re.compile(r"\b(?:wcag|a11y|accessibility)\b", re.IGNORECASE),
        re.compile(r"\b(?:soc2|fedramp|nist)\b", re.IGNORECASE),
        re.compile(r"\bwhite[\-\s]?label\b", re.IGNORECASE),
        re.compile(r"\bmulti[\-\s]?tenant\b", re.IGNORECASE),
        re.compile(r"\bdata residency\b", re.IGNORECASE),
        re.compile(r"\bdisaster recovery\b", re.IGNORECASE),
        re.compile(r"\boffline[\-\s]?first\b", re.IGNORECASE),
        re.compile(r"\bbiometric(?:\s+login|\s+auth(?:entication)?)?\b", re.IGNORECASE),
        re.compile(r"\b(?:aml|kyc)(?:\s*/\s*(?:aml|kyc))?\b", re.IGNORECASE),
        re.compile(r"\b(?:raw\s+card\s+data|cardholder\s+data|tokeniz(?:ed|ation))\b", re.IGNORECASE),
    )
    _OUT_OF_SCOPE_RE = re.compile(
        r"\b(?:out\s+of\s+scope|not\s+in\s+scope|excluded\s+from\s+scope|"
        r"not\s+included|deferred\s+from\s+v?\d+|future\s+version|future\s+enhancement)\b",
        re.IGNORECASE,
    )

    def _split_sections(self, text: str) -> dict[str, list[str]]:
        sections: dict[str, list[str]] = {}
        current_section: str | None = None

        for line in text.splitlines():
            match = self._SECTION_RE.match(line.strip())
            if match:
                current_section = match.group(1).title()
                sections.setdefault(current_section, [])
                continue
            if current_section is not None:
                sections[current_section].append(line)

        return sections

    def _extract_bullets(self, lines: list[str]) -> list[str]:
        bullets: list[str] = []
        for line in lines:
            match = self._BULLET_RE.match(line)
            if not match:
                continue
            bullet = match.group(1).strip()
            if bullet:
                bullets.append(bullet)
        return bullets

    def _extract_items(self, lines: list[str]) -> list[str]:
        """Extract bullet items or split free-form quality clauses into atomic items."""
        bullets = self._extract_bullets(lines)
        if bullets:
            return bullets
        paragraph = self._extract_paragraph(lines)
        if not paragraph:
            return []
        items: list[str] = []
        for sentence in self._split_sentences(paragraph):
            expanded = self._expand_compound_nfr_items(sentence)
            if expanded:
                items.extend(expanded)
                continue
            cleaned = sentence.strip().rstrip(".").strip()
            if cleaned:
                items.append(cleaned)
        return items

    def _extract_actor_names(self, lines: list[str]) -> list[str]:
        actors: list[str] = []
        for bullet in self._extract_bullets(lines):
            actors.extend(part.strip() for part in bullet.split(",") if part.strip())
        return actors

    def _extract_paragraph(self, lines: list[str]) -> str:
        return " ".join(line.strip() for line in lines if line.strip())

    def _split_sentences(self, paragraph: str) -> list[str]:
        chunks = self._SENTENCE_SPLIT_RE.split(paragraph.strip())
        return [chunk.strip() for chunk in chunks if chunk.strip()]

    @staticmethod
    def _protect_numeric_commas(text: str) -> str:
        return re.sub(r"(?<=\d),(?=\d{3}\b)", "__THOUSANDS_COMMA__", text)

    def _split_choice_list(self, text: str) -> list[str]:
        protected = self._protect_numeric_commas(text.strip())
        normalized = re.sub(r"\s*,\s*(?:and\s+)?", ", ", protected, flags=re.IGNORECASE)
        normalized = re.sub(r"\s+or\s+", ", ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\s+and\s+", ", ", normalized, flags=re.IGNORECASE)
        return [
            part.strip(" .,;:()").replace("__THOUSANDS_COMMA__", ",")
            for part in normalized.split(",")
            if part.strip(" .,;:()")
        ]

    def _detect_nfr_concern(self, text: str) -> str | None:
        lowered = text.casefold()
        if re.search(r"\b(high(?:ly)?\s+available|availability|uptime|downtime|reliab\w*|sla|slo)\b", lowered):
            return "availability"
        if re.search(
            r"\b(encrypt(?:ed|ion)?|aes(?:-\d+)?|tls|ssl|secure|security|privacy|"
            r"authenticat\w*|authoriz\w*|biometric|2fa|mfa|audit|compliance|gdpr|"
            r"hipaa|pci|soc2|fedramp|nist)\b",
            lowered,
        ):
            return "security"
        if re.search(r"\b(peak[\-\s]?load|throughput|latency|response time|p95|p99|concurrent|scalab\w*|performance)\b", lowered):
            return "performance"
        if re.search(r"\bmobile[\-\s]?(?:first|friendly)?\b", lowered):
            return "mobile"
        if re.search(r"\b(accessibility|wcag|a11y)\b", lowered):
            return "accessibility"
        if re.search(r"\b(multilingual|localiz(?:ation|e)|i18n|rtl|ltr|language support|arabic|english)\b", lowered):
            return "localization"
        if re.search(r"\b(backup|retention|restore|recovery|rto|rpo|observability|tracing|monitoring|offline|sync)\b", lowered):
            return "operations"
        return None

    def _normalize_nfr_fragment(self, text: str) -> str:
        cleaned = text.strip().rstrip(".").strip()
        lowered = cleaned.casefold()

        if re.fullmatch(r"(?:compliant|compliance|regulatory compliance)", lowered):
            return "maintain regulatory compliance"

        if re.search(r"\b(?:raw\s+card\s+data|cardholder\s+data|tokeniz(?:ed|ation))\b", lowered):
            if "certified" in lowered or "provider" in lowered:
                return "store card data only through a certified tokenization provider"
            return "avoid storing raw card data"

        if re.search(r"\b(?:aml|kyc)\b", lowered):
            if re.search(r"\baml\s*/\s*kyc\b|\bkyc\s*/\s*aml\b", lowered) or (
                "aml" in lowered and "kyc" in lowered
            ):
                return "maintain AML/KYC compliance"
            if "aml" in lowered:
                return "maintain AML compliance"
            return "maintain KYC compliance"

        if re.search(r"\b(high(?:ly)?\s+available|availability|uptime|downtime|reliab\w*)\b", lowered):
            percent = re.search(r"\b\d{1,2}(?:\.\d+)?%\b", cleaned)
            if percent:
                return f"maintain {percent.group(0)} availability"
            return "maintain high availability"

        if re.search(r"\bencrypt(?:ed|ion)?\b", lowered) or re.search(r"\b(aes(?:-\d+)?|tls|ssl)\b", lowered):
            suffix_match = re.search(r"\busing\b.+$", cleaned, flags=re.IGNORECASE)
            suffix = f" {suffix_match.group(0)}" if suffix_match else ""
            if re.search(r"\bat rest\b", lowered):
                return f"encrypt sensitive data at rest{suffix}"
            if re.search(r"\bin transit\b", lowered):
                return f"encrypt sensitive data in transit{suffix}"
            return "encrypt sensitive data"

        compliance_frameworks = (
            ("pci-dss", "PCI-DSS"),
            ("pci", "PCI-DSS"),
            ("hipaa", "HIPAA"),
            ("gdpr", "GDPR"),
            ("soc2", "SOC 2"),
            ("fedramp", "FedRAMP"),
            ("nist", "NIST"),
        )
        for pattern, label in compliance_frameworks:
            if re.search(rf"\b{re.escape(pattern)}\b", lowered):
                return f"maintain {label} compliance"

        if re.search(r"\bmobile[\-\s]?first\b", lowered):
            return "support a mobile-first interface"
        if re.search(r"\bmobile[\-\s]?friendly\b", lowered):
            return "support mobile-friendly interfaces"

        if re.search(r"\boffline\b", lowered):
            return "support offline capability"

        if re.search(r"\bqueued payments?\b", lowered) and re.search(r"\bconflict[\-\s]?safe\s+sync\b", lowered):
            return "support queued payments with conflict-safe sync"

        if re.search(r"\bidempotent\b", lowered):
            if re.search(r"\b(transaction|transactions|payment|payments)\b", lowered):
                return "enforce idempotent transaction processing"
            return "enforce idempotent operations"

        if re.search(r"\bmulti[\-\s]?tenant\b", lowered) and re.search(r"\bdata isolation\b|\bisolation\b", lowered):
            return "enforce multi-tenant data isolation"

        if re.search(r"\b(?:rto|rpo)\b", lowered):
            metric = "RTO" if "rto" in lowered else "RPO"
            threshold = re.search(
                r"\b(?:under|within|<=?|less than)\s+(\d+(?:\.\d+)?\s*(?:ms|milliseconds?|seconds?|minutes?|hours?))\b",
                cleaned,
                flags=re.IGNORECASE,
            )
            if threshold:
                return f"meet {metric} under {threshold.group(1)}"
            return f"meet {metric} recovery objective"

        if re.search(r"\bdata retention\b|\bretention\b", lowered):
            if "configurable" in lowered:
                return "support configurable data retention"
            return "support data retention policy"

        if re.search(r"\b(?:throughput|events?\s+per\s+second|events?/sec)\b", lowered):
            throughput = re.search(
                r"\b(\d[\d,]*)\s+events?\s+per\s+second\b",
                cleaned,
                flags=re.IGNORECASE,
            )
            focus_match = re.search(r"^(.+?)\s+throughput\b", cleaned, flags=re.IGNORECASE)
            focus = (focus_match.group(1).strip(" .,;:") if focus_match else "processing").lower()
            focus = re.sub(r"^(?:support|maintain|provide|meet)\s+", "", focus, flags=re.IGNORECASE)
            if throughput:
                return f"support {focus} throughput of {throughput.group(1)} events per second"
            return f"support {focus} throughput"

        if re.search(r"\b(?:p95|p99|latency|response time)\b", lowered):
            percentile = re.search(r"\bp(?:95|99)\b", cleaned, flags=re.IGNORECASE)
            threshold = re.search(
                r"\b(?:under|within|<=?|less than)\s+(\d+(?:\.\d+)?\s*(?:ms|milliseconds?|seconds?|s))\b",
                cleaned,
                flags=re.IGNORECASE,
            )
            concurrency_target = re.search(r"\b(\d[\d,]*)\s+concurrent users?\b", cleaned, flags=re.IGNORECASE)
            parts = ["meet"]
            if percentile:
                parts.append(percentile.group(0).lower())
            if threshold:
                parts.append(f"under {threshold.group(1)}")
            parts.append("response-time SLO")
            if concurrency_target:
                parts.append(f"for {concurrency_target.group(1)} concurrent users")
            return " ".join(parts)

        if re.search(r"\b(responsive|peak[\-\s]?load|throughput|latency|response time|p95|p99|concurrent|performance)\b", lowered):
            if re.search(r"\bpeak[\-\s]?load\b", lowered):
                return "maintain responsive performance under peak load"
            concurrency_target = re.search(r"\b(\d[\d,]*)\s+concurrent users?\b", cleaned, flags=re.IGNORECASE)
            if concurrency_target:
                return f"scale to {concurrency_target.group(1)} concurrent users"
            if re.search(r"\bconcurrent\b", lowered):
                return "maintain responsive performance for concurrent users"
            if re.search(r"\bscalab\w*\b", lowered):
                return cleaned[:1].lower() + cleaned[1:] if cleaned else cleaned
            if lowered.startswith("maintain "):
                return cleaned[:1].lower() + cleaned[1:] if cleaned else cleaned
            return f"maintain {cleaned}"

        if re.search(r"\b(accessible|accessibility|wcag|a11y)\b", lowered):
            if re.search(r"\bwcag\b", lowered):
                level = re.search(r"\bwcag\s+([a]{1,3})\b", cleaned, flags=re.IGNORECASE)
                if level:
                    return f"meet WCAG {level.group(1).upper()} accessibility requirements"
            return "meet accessibility requirements"

        if re.search(r"\b(?:observability|observable|distributed tracing|tracing|telemetry|monitoring)\b", lowered):
            if re.search(r"\baudit[\-\s]?(?:log|logs|trail|trails)\b", lowered):
                return "provide observability with audit logs"
            if re.search(r"\bdistributed tracing\b|\btracing\b", lowered):
                return "provide distributed tracing observability"
            return "provide observability monitoring"

        if re.search(r"\b(?:arabic|english|rtl|ltr|multilingual|localiz(?:ation|e)|i18n)\b", lowered):
            if re.search(r"\barabic\b", lowered) and re.search(r"\benglish\b", lowered):
                if re.search(r"\brtl\b", lowered) and re.search(r"\bltr\b", lowered):
                    return "support Arabic and English UI with RTL/LTR layout"
                if re.search(r"\brtl\b", lowered):
                    return "support Arabic and English UI with RTL layout"
                if re.search(r"\bltr\b", lowered):
                    return "support Arabic and English UI with LTR layout"
                return "support Arabic and English UI"
            return "support multilingual localization"

        if re.search(r"\bsandbox\b", lowered):
            return "provide sandbox mode for partner bank integration testing"

        if re.search(r"\b(backup|retention|restore|recovery|rto|rpo)\b", lowered):
            return "support backup and recovery objectives"

        if re.search(r"\b(2fa|mfa|multi[\-\s]?factor|two[\-\s]?factor|biometric)\b", lowered):
            return "support multi-factor authentication"

        if re.search(r"\baudit[\-\s]?(?:log|logs|trail|trails)\b", lowered):
            return "keep audit logs for privileged actions"

        return cleaned

    def _expand_compound_nfr_items(self, sentence: str) -> list[str] | None:
        cleaned = sentence.strip().rstrip(".").strip()
        if not cleaned:
            return None

        body = self._clean_req_text(cleaned)
        body = re.sub(r"^(?:be|remain|stay)\s+", "", body, flags=re.IGNORECASE).strip()
        if "," not in body and re.search(r"\band\b", body, flags=re.IGNORECASE) is None:
            return None

        fragments = self._split_choice_list(body)
        if len(fragments) < 2:
            return None

        concerns = [self._detect_nfr_concern(fragment) for fragment in fragments]
        has_dual_encryption = re.search(r"\bat rest\b", body, flags=re.IGNORECASE) and re.search(
            r"\bin transit\b",
            body,
            flags=re.IGNORECASE,
        )
        should_split = (
            len(fragments) >= 3 and len([concern for concern in concerns if concern]) >= 2
        ) or bool(has_dual_encryption)
        if not should_split:
            return None

        expanded: list[str] = []
        for fragment in fragments:
            contextual_fragment = fragment
            if re.search(r"\bencrypt(?:ed|ion)?\b", body, flags=re.IGNORECASE):
                if re.fullmatch(r"(?:at\s+rest|data\s+at\s+rest)", fragment, flags=re.IGNORECASE):
                    contextual_fragment = "encrypt sensitive data at rest"
                elif re.fullmatch(r"(?:in\s+transit|data\s+in\s+transit)", fragment, flags=re.IGNORECASE):
                    contextual_fragment = "encrypt sensitive data in transit"
            normalized = self._normalize_nfr_fragment(contextual_fragment)
            if normalized and normalized not in expanded:
                expanded.append(normalized)
        return expanded or None

    def _find_actor(self, feature_text: str, actors: list[str]) -> str | None:
        feature_lower = feature_text.casefold()
        if "customer support" in feature_lower:
            support_actor = next((actor for actor in actors if "support" in actor.casefold()), None)
            if support_actor:
                return support_actor
        for explicit_role in ("tenant admin", "compliance analyst", "support agent", "merchant"):
            if explicit_role in feature_lower:
                matched_actor = next((actor for actor in actors if explicit_role in actor.casefold()), None)
                if matched_actor:
                    return matched_actor
        for actor in actors:
            actor_words = re.findall(r"\w+", actor.casefold())
            search_terms: list[str] = []
            for word in actor_words:
                search_terms.append(word)
                if len(word) > 2 and not word.endswith("s"):
                    search_terms.append(f"{word}s")
            for word in search_terms:
                m = re.search(r"\b" + re.escape(word) + r"\b", feature_lower)
                if m and m.start() < len(feature_lower) * 0.6:
                    return actor
        return None

    def _is_nfr(self, text: str) -> bool:
        lowered = text.casefold()
        tokens = set(re.findall(r"\w+", lowered))
        return bool(tokens & self._NFR_KEYWORDS) or any(
            pattern.search(lowered) for pattern in self._NFR_PATTERNS
        )

    def _is_out_of_scope(self, text: str) -> bool:
        return self._OUT_OF_SCOPE_RE.search(text) is not None

    def _clean_req_text(self, text: str) -> str:
        cleaned = re.sub(
            r"^(?:the system|it|this system|[A-Za-z][A-Za-z\s]{2,30}?)\s+(?:should|must|shall|will)\s+",
            "",
            text.strip(),
            flags=re.IGNORECASE,
        ).strip()
        cleaned = re.sub(r"^(?:must|should|shall|will)\s+", "", cleaned, flags=re.IGNORECASE).strip()
        optional_match = re.match(
            r"(?P<capability>.+?)\s+is\s+preferred\s+but\s+not\s+required"
            r"(?:\s+for\s+the\s+(?P<scope>.+))?$",
            cleaned,
            flags=re.IGNORECASE,
        )
        if optional_match:
            capability = optional_match.group("capability").strip(" .")
            scope = (optional_match.group("scope") or "initial release").strip(" .")
            return f"provide optional {capability} outside the {scope} baseline"
        return cleaned or text.strip()

    @staticmethod
    def _lowercase_initial_capability(text: str) -> str:
        stripped = text.strip()
        if not stripped:
            return stripped
        first_word = stripped.split()[0].strip(".,;:()")
        if re.fullmatch(r"[A-Z0-9]{2,}(?:[-/][A-Z0-9]{2,})?", first_word):
            return stripped
        return f"{stripped[:1].lower()}{stripped[1:]}"

    @staticmethod
    def _normalize_feature_fragment(text: str) -> str:
        cleaned = text.strip().rstrip(".").strip()
        if not cleaned:
            return cleaned
        if re.match(r"^customer\s+support\b", cleaned, flags=re.IGNORECASE):
            return f"provide {BriefParser._lowercase_initial_capability(cleaned)}"
        cleaned = re.sub(
            r"^(?:customers?|users?|merchants?|admins?|students?|patients?|doctors?|staff)\s+"
            r"(register|book|allow|generate|send|view|record|manage|process|upload|"
            r"download|search|browse|add|create|integrate|track|transfer|pay|analy[sz]e|"
            r"support|provide|enable|schedule|display|show|issue|approve|verify)\b",
            r"\1",
            cleaned,
            flags=re.IGNORECASE,
        )

        if re.match(
            r"^(?:register|book|allow|generate|send|view|record|manage|process|upload|"
            r"download|search|browse|add|create|integrate|track|transfer|pay|analy[sz]e|"
            r"support|provide|enable|schedule|display|show|issue|approve|verify)\b",
            cleaned,
            flags=re.IGNORECASE,
        ):
            return cleaned

        return f"provide {BriefParser._lowercase_initial_capability(cleaned)}"

    def parse(self, text: str) -> list[RequirementItem]:
        sections = self._split_sections(text)
        features = (
            self._extract_bullets(sections.get("Main Features", []))
            + self._extract_bullets(sections.get("Functional Requirements", []))
        )
        actors = (
            self._extract_bullets(sections.get("Target Users", []))
            + self._extract_actor_names(sections.get("Actors", []))
        )
        special_constraints = self._extract_items(
            sections.get("Constraints Or Special Notes", [])
            or sections.get("Constraints or Special Notes", [])
        )
        nfr_constraints = self._extract_items(sections.get("Non-Functional Requirements", []))
        constraints = special_constraints + nfr_constraints
        benefits = [] if nfr_constraints else self._extract_items(sections.get("Expected Benefits", []))

        errors: list[str] = []
        if not features:
            errors.append("Main Features section is missing or has no bullet items.")
        if "Project Title" not in sections and "Project Overview" not in sections:
            errors.append("Brief must contain at least a Project Title or Project Overview.")
        if errors:
            raise BriefValidationError(errors)

        items: list[RequirementItem] = []
        i = 1

        for feature in features:
            normalized_feature = self._normalize_feature_fragment(feature)
            actor = self._find_actor(feature, actors)
            if actor:
                req_text = f"Actor: {actor} — The {actor} should {normalized_feature}."
            else:
                req_text = f"The system should {normalized_feature}."
            source = f"REQ-{i:02d}"
            items.append(
                RequirementItem(
                    line_no=i,
                    source=source,
                    text=req_text,
                    sources=(source,),
                )
            )
            i += 1

        for benefit in benefits:
            if self._is_nfr(benefit) and benefit.strip():
                source = f"REQ-{i:02d}"
                normalized_body = self._normalize_nfr_fragment(self._clean_req_text(benefit.strip().rstrip(".")))
                req_text = f"The system should {normalized_body}."
                items.append(
                    RequirementItem(
                        line_no=i,
                        source=source,
                        text=req_text,
                        sources=(source,),
                    )
                )
                i += 1

        for constraint in constraints:
            if self._is_out_of_scope(constraint):
                continue
            if self._is_nfr(constraint) or constraint.strip():
                source = f"REQ-{i:02d}"
                body = self._clean_req_text(constraint)
                if self._is_nfr(constraint):
                    body = self._normalize_nfr_fragment(body)
                req_text = f"The system should {body}."
                items.append(
                    RequirementItem(
                        line_no=i,
                        source=source,
                        text=req_text,
                        sources=(source,),
                    )
                )
                i += 1

        return items
