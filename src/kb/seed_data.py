from __future__ import annotations
from src.kb.vector_store import KnowledgeBase


ESTIMATION_DOCS: list[dict] = [
    # ── Category 1: Historical records (Desharnais & Maxwell datasets) ────────
    {
        "id": "hist_01",
        "text": "Desharnais P1: Payroll system, batch processing, 3 ILF 8 EIF. "
                "FP=491. Actual effort: 2520 person-hours. Team: 5 devs, 14 months. "
                "Domain: MIS. Complexity band: high (4).",
        "metadata": {"category":"historical","complexity_band":4,"domain":"mis",
                     "fp_count":491,"actual_hours":2520,"team_size":5},
    },
    {
        "id": "hist_02",
        "text": "Desharnais P3: Inventory management with reporting module. "
                "FP=267. Actual effort: 1152 person-hours. Team: 3, 9 months. "
                "Domain: MIS. Complexity band: medium (3).",
        "metadata": {"category":"historical","complexity_band":3,"domain":"mis",
                     "fp_count":267,"actual_hours":1152,"team_size":3},
    },
    {
        "id": "hist_03",
        "text": "Desharnais P7: Customer order processing with integration to ERP. "
                "FP=723. Actual effort: 4320 person-hours. Team: 6, 18 months. "
                "Domain: e-commerce. Complexity band: very high (5).",
        "metadata": {"category":"historical","complexity_band":5,"domain":"ecommerce",
                     "fp_count":723,"actual_hours":4320,"team_size":6},
    },
    {
        "id": "hist_04",
        "text": "Desharnais P10: Simple CRUD web module, 3 entities, 2 user roles. "
                "FP=98. Actual effort: 320 person-hours. Team: 2, 5 months. "
                "Domain: web. Complexity band: low (2).",
        "metadata": {"category":"historical","complexity_band":2,"domain":"web",
                     "fp_count":98,"actual_hours":320,"team_size":2},
    },
    {
        "id": "hist_05",
        "text": "Desharnais P14: HR leave and attendance system. "
                "FP=310. Actual effort: 1440 person-hours. Team: 3, 10 months. "
                "Domain: HR. Complexity band: medium (3).",
        "metadata": {"category":"historical","complexity_band":3,"domain":"hr",
                     "fp_count":310,"actual_hours":1440,"team_size":3},
    },
    {
        "id": "hist_06",
        "text": "Desharnais P18: Financial reporting with multi-currency support. "
                "FP=156. Actual effort: 840 person-hours. Team: 2, 7 months. "
                "Domain: finance. Complexity band: medium (3).",
        "metadata": {"category":"historical","complexity_band":3,"domain":"finance",
                     "fp_count":156,"actual_hours":840,"team_size":2},
    },
    {
        "id": "hist_07",
        "text": "Desharnais P22: Clinical patient registration and scheduling. "
                "FP=445. Actual effort: 2160 person-hours. Team: 4, 12 months. "
                "Domain: healthcare. Complexity band: high (4).",
        "metadata": {"category":"historical","complexity_band":4,"domain":"healthcare",
                     "fp_count":445,"actual_hours":2160,"team_size":4},
    },
    {
        "id": "hist_08",
        "text": "Desharnais P25: University course registration portal, 5 user types. "
                "FP=512. Actual effort: 2880 person-hours. Team: 5, 14 months. "
                "Domain: education. Complexity band: high (4).",
        "metadata": {"category":"historical","complexity_band":4,"domain":"education",
                     "fp_count":512,"actual_hours":2880,"team_size":5},
    },
    {
        "id": "hist_09",
        "text": "Desharnais P31: E-commerce catalog with search and filters. "
                "FP=389. Actual effort: 1728 person-hours. Team: 4, 11 months. "
                "Domain: e-commerce. Complexity band: medium-high (3).",
        "metadata": {"category":"historical","complexity_band":3,"domain":"ecommerce",
                     "fp_count":389,"actual_hours":1728,"team_size":4},
    },
    {
        "id": "hist_10",
        "text": "Desharnais P38: Simple configuration and admin panel. "
                "FP=62. Actual effort: 160 person-hours. Team: 1, 3 months. "
                "Domain: web. Complexity band: very low (1).",
        "metadata": {"category":"historical","complexity_band":1,"domain":"web",
                     "fp_count":62,"actual_hours":160,"team_size":1},
    },
    {
        "id": "hist_11",
        "text": "Maxwell M4: Telecom billing system with CDR processing and tariff engine. "
                "FP=1840. Actual effort: 9600 person-hours. Team: 9, 26 months. "
                "Domain: telecom. Complexity band: very high (5).",
        "metadata": {"category":"historical","complexity_band":5,"domain":"telecom",
                     "fp_count":1840,"actual_hours":9600,"team_size":9},
    },
    {
        "id": "hist_12",
        "text": "Maxwell M9: Insurance claims processing with workflow engine. "
                "FP=920. Actual effort: 5040 person-hours. Team: 7, 19 months. "
                "Domain: insurance. Complexity band: very high (5).",
        "metadata": {"category":"historical","complexity_band":5,"domain":"insurance",
                     "fp_count":920,"actual_hours":5040,"team_size":7},
    },
    {
        "id": "hist_13",
        "text": "Maxwell M15: Logistics tracking with GPS integration and alerts. "
                "FP=580. Actual effort: 2880 person-hours. Team: 5, 15 months. "
                "Domain: logistics. Complexity band: high (4).",
        "metadata": {"category":"historical","complexity_band":4,"domain":"logistics",
                     "fp_count":580,"actual_hours":2880,"team_size":5},
    },
    {
        "id": "hist_14",
        "text": "Maxwell M21: Library management system with OPAC and borrowing. "
                "FP=228. Actual effort: 960 person-hours. Team: 3, 8 months. "
                "Domain: library. Complexity band: low (2).",
        "metadata": {"category":"historical","complexity_band":2,"domain":"library",
                     "fp_count":228,"actual_hours":960,"team_size":3},
    },
    {
        "id": "hist_15",
        "text": "Maxwell M27: Real-time IoT sensor dashboard with alerting. "
                "FP=344. Actual effort: 1920 person-hours. Team: 4, 12 months. "
                "Domain: IoT. Complexity band: medium-high (3).",
        "metadata": {"category":"historical","complexity_band":3,"domain":"iot",
                     "fp_count":344,"actual_hours":1920,"team_size":4},
    },
    {
        "id": "hist_16",
        "text": "Maxwell M33: CRM lead tracking with email automation. "
                "FP=415. Actual effort: 2016 person-hours. Team: 4, 12 months. "
                "Domain: CRM. Complexity band: high (4).",
        "metadata": {"category":"historical","complexity_band":4,"domain":"crm",
                     "fp_count":415,"actual_hours":2016,"team_size":4},
    },
    {
        "id": "hist_17",
        "text": "Maxwell M40: SaaS billing with Stripe integration and invoicing. "
                "FP=290. Actual effort: 1344 person-hours. Team: 3, 9 months. "
                "Domain: fintech. Complexity band: medium (3).",
        "metadata": {"category":"historical","complexity_band":3,"domain":"fintech",
                     "fp_count":290,"actual_hours":1344,"team_size":3},
    },
    {
        "id": "hist_18",
        "text": "Maxwell M46: Social platform with feed, follows, and moderation. "
                "FP=678. Actual effort: 3840 person-hours. Team: 6, 17 months. "
                "Domain: social. Complexity band: high (4).",
        "metadata": {"category":"historical","complexity_band":4,"domain":"social",
                     "fp_count":678,"actual_hours":3840,"team_size":6},
    },
    {
        "id": "hist_19",
        "text": "Maxwell M52: Payment gateway with PCI-DSS compliance and 3DS. "
                "FP=510. Actual effort: 3360 person-hours. Team: 5, 16 months. "
                "Domain: fintech. Complexity band: very high (5).",
        "metadata": {"category":"historical","complexity_band":5,"domain":"fintech",
                     "fp_count":510,"actual_hours":3360,"team_size":5},
    },
    {
        "id": "hist_20",
        "text": "Maxwell M58: LMS with quiz engine, progress tracking, certificates. "
                "FP=395. Actual effort: 1920 person-hours. Team: 4, 12 months. "
                "Domain: education. Complexity band: medium (3).",
        "metadata": {"category":"historical","complexity_band":3,"domain":"education",
                     "fp_count":395,"actual_hours":1920,"team_size":4},
    },
    {
        "id": "hist_21",
        "text": "Synthetic S1: NFR performance optimization — caching layer + CDN. "
                "Actual effort: 480 person-hours. Team: 2, 3 months. "
                "Complexity band: medium (3). Type: NFR.",
        "metadata": {"category":"historical","complexity_band":3,"domain":"platform",
                     "fp_count":0,"actual_hours":480,"team_size":2},
    },
    {
        "id": "hist_22",
        "text": "Synthetic S2: NFR security hardening — pen-test remediation + OWASP fixes. "
                "Actual effort: 560 person-hours. Team: 2, 4 months. "
                "Complexity band: high (4). Type: NFR.",
        "metadata": {"category":"historical","complexity_band":4,"domain":"security",
                     "fp_count":0,"actual_hours":560,"team_size":2},
    },
    {
        "id": "hist_23",
        "text": "Synthetic S3: Notification service — email/SMS/push with retry logic. "
                "Actual effort: 320 person-hours. Team: 2, 5 weeks. "
                "Complexity band: medium (3). Type: FR.",
        "metadata": {"category":"historical","complexity_band":3,"domain":"backend",
                     "fp_count":0,"actual_hours":320,"team_size":2},
    },
    {
        "id": "hist_24",
        "text": "Synthetic S4: Admin dashboard with role-based access and audit trail. "
                "Actual effort: 240 person-hours. Team: 2, 4 weeks. "
                "Complexity band: medium (3). Type: FR.",
        "metadata": {"category":"historical","complexity_band":3,"domain":"web",
                     "fp_count":0,"actual_hours":240,"team_size":2},
    },
    {
        "id": "hist_25",
        "text": "Synthetic S5: Data migration — legacy DB to new schema, ETL pipeline. "
                "Actual effort: 400 person-hours. Team: 2, 6 weeks. "
                "Complexity band: high (4). Type: FR.",
        "metadata": {"category":"historical","complexity_band":4,"domain":"data",
                     "fp_count":0,"actual_hours":400,"team_size":2},
    },
    {
        "id": "hist_26",
        "text": "Synthetic S6: REST API design + OpenAPI spec + rate limiting. "
                "Actual effort: 160 person-hours. Team: 1, 3 weeks. "
                "Complexity band: low (2). Type: FR.",
        "metadata": {"category":"historical","complexity_band":2,"domain":"backend",
                     "fp_count":0,"actual_hours":160,"team_size":1},
    },
    {
        "id": "hist_27",
        "text": "Synthetic S7: NFR availability — HA setup, failover, 99.9% SLA. "
                "Actual effort: 720 person-hours. Team: 3, 5 months. "
                "Complexity band: very high (5). Type: NFR.",
        "metadata": {"category":"historical","complexity_band":5,"domain":"platform",
                     "fp_count":0,"actual_hours":720,"team_size":3},
    },
    {
        "id": "hist_28",
        "text": "Synthetic S8: Multi-language localization (i18n) for 5 languages. "
                "Actual effort: 200 person-hours. Team: 1, 3 weeks. "
                "Complexity band: medium (3). Type: NFR.",
        "metadata": {"category":"historical","complexity_band":3,"domain":"frontend",
                     "fp_count":0,"actual_hours":200,"team_size":1},
    },
    {
        "id": "hist_29",
        "text": "Synthetic S9: Reporting module — PDF/Excel export with filters. "
                "Actual effort: 280 person-hours. Team: 2, 4 weeks. "
                "Complexity band: medium (3). Type: FR.",
        "metadata": {"category":"historical","complexity_band":3,"domain":"data",
                     "fp_count":0,"actual_hours":280,"team_size":2},
    },
    {
        "id": "hist_30",
        "text": "Synthetic S10: Mobile-responsive UI redesign, 12 screens. "
                "Actual effort: 360 person-hours. Team: 2, 5 weeks. "
                "Complexity band: medium (3). Type: FR.",
        "metadata": {"category":"historical","complexity_band":3,"domain":"frontend",
                     "fp_count":0,"actual_hours":360,"team_size":2},
    },

    # ── Category 2: COCOMO II calibration points ─────────────────────────────
    {
        "id": "cocomo_01",
        "text": "COCOMO II Organic mode: small familiar project 2 KLOC. "
                "Team: 3 devs, EAF=1.0 (all nominal drivers). "
                "Estimated: 6.4 PM = 1024 person-hours. Complexity: medium (3).",
        "metadata": {"category":"cocomo","complexity_band":3,"actual_hours":1024,
                     "team_size":3,"fp_count":0},
    },
    {
        "id": "cocomo_02",
        "text": "COCOMO II Semi-detached: medium project 10 KLOC with DB integration. "
                "Team: 6 devs, EAF=1.12 (high complexity driver). "
                "Estimated: 36 PM = 5760 person-hours. Complexity: high (4).",
        "metadata": {"category":"cocomo","complexity_band":4,"actual_hours":5760,
                     "team_size":6,"fp_count":0},
    },
    {
        "id": "cocomo_03",
        "text": "COCOMO II Embedded mode: 32 KLOC real-time system with tight constraints. "
                "Team: 10 devs, EAF=1.35 (very high reliability+complexity). "
                "Estimated: 188 PM = 30080 person-hours. Complexity: very high (5).",
        "metadata": {"category":"cocomo","complexity_band":5,"actual_hours":30080,
                     "team_size":10,"fp_count":0},
    },
    {
        "id": "cocomo_04",
        "text": "COCOMO II with RUSE reuse factor: 5 KLOC reusing 60% existing code. "
                "Team: 4 devs, EAF=0.85 (high reuse, experienced team). "
                "Estimated: 14 PM = 2240 person-hours. Complexity: medium (3).",
        "metadata": {"category":"cocomo","complexity_band":3,"actual_hours":2240,
                     "team_size":4,"fp_count":0},
    },
    {
        "id": "cocomo_05",
        "text": "COCOMO II Post-Architecture: 8 KLOC web service with microservices. "
                "Team: 5, EAF=1.20 (high architecture complexity). "
                "Estimated: 28 PM = 4480 person-hours. Complexity: high (4).",
        "metadata": {"category":"cocomo","complexity_band":4,"actual_hours":4480,
                     "team_size":5,"fp_count":0},
    },
    {
        "id": "cocomo_06",
        "text": "COCOMO II small module, 0.5 KLOC prototype or spike. "
                "Team: 1-2 devs, EAF=0.90 (familiar domain). "
                "Estimated: 1.2 PM = 192 person-hours. Complexity: low (2).",
        "metadata": {"category":"cocomo","complexity_band":2,"actual_hours":192,
                     "team_size":2,"fp_count":0},
    },
    {
        "id": "cocomo_07",
        "text": "COCOMO II very small script/config module, 0.1 KLOC. "
                "Team: 1 dev. Estimated: 0.25 PM = 40 person-hours. "
                "Complexity: trivial (1).",
        "metadata": {"category":"cocomo","complexity_band":1,"actual_hours":40,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "cocomo_08",
        "text": "COCOMO II with SCED compression: 6-month project compressed to 4 months. "
                "Effort increases 23% due to staffing peaks. Base: 2000h → Actual: 2460h. "
                "Complexity: medium-high (3).",
        "metadata": {"category":"cocomo","complexity_band":3,"actual_hours":2460,
                     "team_size":4,"fp_count":0},
    },
    {
        "id": "cocomo_09",
        "text": "COCOMO II legacy re-engineering project, 15 KLOC modernisation. "
                "Team: 7, EAF=1.40 (required rework, poor documentation). "
                "Estimated: 72 PM = 11520 person-hours. Complexity: very high (5).",
        "metadata": {"category":"cocomo","complexity_band":5,"actual_hours":11520,
                     "team_size":7,"fp_count":0},
    },
    {
        "id": "cocomo_10",
        "text": "COCOMO II NFR-heavy: security + compliance + performance requirements "
                "add an average 35% overhead to functional effort baseline. "
                "NFR overhead coefficient: 1.35x for any NFR task.",
        "metadata": {"category":"cocomo","complexity_band":3,"actual_hours":0,
                     "team_size":0,"fp_count":0},
    },

    # ── Category 3: Task-type patterns (Jones 2007 + industry baselines) ─────
    {
        "id": "pattern_01",
        "text": "Authentication module: JWT + session management typically 24-32h. "
                "OAuth2 social login adds 16h. MFA (TOTP/SMS) adds 12h. "
                "Security review: +8h. Total OAuth2+MFA: 40-52h.",
        "metadata": {"category":"pattern","complexity_band":3,"actual_hours":36,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_02",
        "text": "CRUD API module (REST, 5 entities): design + implementation + tests = 32-48h. "
                "With pagination, filtering, sorting: +16h. "
                "OpenAPI spec documentation: +8h. Total: 48-72h.",
        "metadata": {"category":"pattern","complexity_band":3,"actual_hours":48,
                     "team_size":2,"fp_count":0},
    },
    {
        "id": "pattern_03",
        "text": "Database schema design + migrations for medium system (10-15 tables): 24-40h. "
                "Includes ER design, indexing strategy, seed data. "
                "Complex relational system (30+ tables): 60-80h.",
        "metadata": {"category":"pattern","complexity_band":3,"actual_hours":32,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_04",
        "text": "Real-time notification service (WebSocket + push + email): 48-64h. "
                "Retry logic + dead-letter queue: +16h. "
                "Multi-channel (email/SMS/push): +24h. Total: 72-104h.",
        "metadata": {"category":"pattern","complexity_band":4,"actual_hours":64,
                     "team_size":2,"fp_count":0},
    },
    {
        "id": "pattern_05",
        "text": "Reporting module with PDF/Excel export: 32-48h base. "
                "Dynamic filters + aggregation queries: +20h. "
                "Scheduled email delivery: +12h. Total: 52-80h.",
        "metadata": {"category":"pattern","complexity_band":3,"actual_hours":48,
                     "team_size":2,"fp_count":0},
    },
    {
        "id": "pattern_06",
        "text": "Third-party API integration (payment gateway, Stripe/PayPal): 40-56h. "
                "Includes webhook handling, idempotency, refund flows. "
                "PCI-DSS compliance layer adds 24-32h extra.",
        "metadata": {"category":"pattern","complexity_band":4,"actual_hours":56,
                     "team_size":2,"fp_count":0},
    },
    {
        "id": "pattern_07",
        "text": "Search and filtering feature (DB-based full-text search): 24-40h. "
                "Elasticsearch/OpenSearch integration: 48-64h. "
                "Faceted search + ranking: +20h.",
        "metadata": {"category":"pattern","complexity_band":3,"actual_hours":40,
                     "team_size":2,"fp_count":0},
    },
    {
        "id": "pattern_08",
        "text": "Role-based access control (RBAC) system: 32-48h. "
                "Includes permission matrix, middleware guards, UI conditionals. "
                "Attribute-based (ABAC) adds 32h complexity.",
        "metadata": {"category":"pattern","complexity_band":3,"actual_hours":40,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_09",
        "text": "File upload and storage module (S3/local): 16-24h. "
                "Image resizing + thumbnail generation: +12h. "
                "Virus scanning + validation pipeline: +16h. Total: 32-52h.",
        "metadata": {"category":"pattern","complexity_band":2,"actual_hours":24,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_10",
        "text": "Performance NFR: load testing setup + bottleneck analysis + caching = 40-60h. "
                "Redis/Memcached integration: 16h. CDN configuration: 8h. "
                "Query optimisation for 10k concurrent users: 24-40h.",
        "metadata": {"category":"pattern","complexity_band":4,"actual_hours":56,
                     "team_size":2,"fp_count":0},
    },
    {
        "id": "pattern_11",
        "text": "Simple CRUD for single entity (1 table, 3 endpoints): 8-14 hours. "
                "Includes basic validation and unit tests. Complexity: low (2).",
        "metadata": {"category":"pattern","complexity_band":2,"actual_hours":11,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_12",
        "text": "Config/settings module with key-value storage and admin UI: 5-9 hours. "
                "No external dependencies. Complexity: trivial (1).",
        "metadata": {"category":"pattern","complexity_band":1,"actual_hours":7,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_13",
        "text": "User profile page with avatar upload and edit form: 10-18 hours. "
                "Includes validation and storage integration. Complexity: low (2).",
        "metadata": {"category":"pattern","complexity_band":2,"actual_hours":14,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_14",
        "text": "Static landing page or dashboard shell with navigation: 4-8 hours. "
                "No backend logic. Complexity: trivial (1).",
        "metadata": {"category":"pattern","complexity_band":1,"actual_hours":6,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_15",
        "text": "Search and filter feature with pagination and keyword highlighting: 14-20 hours. "
                "Includes debounce, server-side query, and result rendering. Complexity: low (2).",
        "metadata": {"category":"pattern","complexity_band":2,"actual_hours":17,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_16",
        "text": "Data export feature (CSV and Excel) from existing list view: 12-18 hours. "
                "Includes column mapping, large dataset streaming, progress indicator. Complexity: low (2).",
        "metadata": {"category":"pattern","complexity_band":2,"actual_hours":15,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_17",
        "text": "Simple analytics dashboard widget with chart (bar or line): 12-20 hours. "
                "Includes aggregation query, chart library integration, responsive layout. Complexity: low (2).",
        "metadata": {"category":"pattern","complexity_band":2,"actual_hours":16,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_18",
        "text": "Role-based list view with filters, sorting, and bulk action: 10-18 hours. "
                "Includes RBAC check, query builder, and UI state management. Complexity: low (2).",
        "metadata": {"category":"pattern","complexity_band":2,"actual_hours":14,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_19",
        "text": "IoT sensor data ingestion pipeline (MQTT broker + time-series DB): 32-48h. "
                "Includes device auth and schema validation. Complexity: high (4).",
        "metadata": {"category":"pattern","complexity_band":4,"actual_hours":40,
                     "team_size":2,"fp_count":0},
    },
    {
        "id": "pattern_20",
        "text": "Real-time alerting with threshold configuration and notification dispatch: 24-36h. "
                "WebSocket push + email fallback. Complexity: medium-high (3).",
        "metadata": {"category":"pattern","complexity_band":3,"actual_hours":30,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_21",
        "text": "HL7 FHIR integration for health data exchange between facilities: 64-96h. "
                "Includes message mapping, validation, and compliance checks. Complexity: very high (5).",
        "metadata": {"category":"pattern","complexity_band":5,"actual_hours":80,
                     "team_size":2,"fp_count":0},
    },
    {
        "id": "pattern_22",
        "text": "HIPAA-compliant PHI storage with encryption at rest and in transit: 40-56h. "
                "Audit trail + access control. Complexity: high (4).",
        "metadata": {"category":"pattern","complexity_band":4,"actual_hours":48,
                     "team_size":2,"fp_count":0},
    },
    {
        "id": "pattern_23",
        "text": "KYC identity verification workflow with document upload and status tracking: 32-48h. "
                "Third-party provider integration. Complexity: high (4).",
        "metadata": {"category":"pattern","complexity_band":4,"actual_hours":40,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_24",
        "text": "PCI-DSS payment gateway integration with tokenization and 3DS: 48-72h. "
                "Webhook handling + idempotency keys. Complexity: very high (5).",
        "metadata": {"category":"pattern","complexity_band":5,"actual_hours":60,
                     "team_size":2,"fp_count":0},
    },
    {
        "id": "pattern_25",
        "text": "Social media feed with infinite scroll, likes, and comments: 32-48h. "
                "Includes pagination, optimistic UI, and real-time updates. Complexity: high (4).",
        "metadata": {"category":"pattern","complexity_band":4,"actual_hours":40,
                     "team_size":2,"fp_count":0},
    },
    {
        "id": "pattern_26",
        "text": "Content moderation system with automated flagging and human review queue: 40-60h. "
                "ML integration + moderation workflow. Complexity: high (4).",
        "metadata": {"category":"pattern","complexity_band":4,"actual_hours":50,
                     "team_size":2,"fp_count":0},
    },
    {
        "id": "pattern_27",
        "text": "LMS quiz engine with multiple question types, time limits, and auto-grading: 32-48h. "
                "Complexity: high (4).",
        "metadata": {"category":"pattern","complexity_band":4,"actual_hours":40,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_28",
        "text": "Certificate generation and digital signing (PDF with QR code): 16-24h. "
                "Template engine + verification endpoint. Complexity: medium (3).",
        "metadata": {"category":"pattern","complexity_band":3,"actual_hours":20,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_29",
        "text": "Subscription management with plan upgrades, downgrades, and proration: 32-48h. "
                "Stripe webhooks + billing logic. Complexity: high (4).",
        "metadata": {"category":"pattern","complexity_band":4,"actual_hours":40,
                     "team_size":2,"fp_count":0},
    },
    {
        "id": "pattern_30",
        "text": "Failed payment dunning flow with retry schedule and customer notifications: 20-32h. "
                "State machine + email sequences. Complexity: medium (3).",
        "metadata": {"category":"pattern","complexity_band":3,"actual_hours":26,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_31",
        "text": "Payroll calculation module with tax tables, deductions, and payslip generation: 40-64h. "
                "Domain logic heavy. Complexity: very high (5).",
        "metadata": {"category":"pattern","complexity_band":5,"actual_hours":52,
                     "team_size":2,"fp_count":0},
    },
    {
        "id": "pattern_32",
        "text": "Leave management with multi-level approval workflow and calendar integration: 24-40h. "
                "Complexity: medium (3).",
        "metadata": {"category":"pattern","complexity_band":3,"actual_hours":32,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_33",
        "text": "Horizontal auto-scaling setup with load balancer and health checks: 24-40h. "
                "NFR infrastructure task. Complexity: high (4).",
        "metadata": {"category":"pattern","complexity_band":4,"actual_hours":32,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_34",
        "text": "Redis caching layer for API responses and session management: 16-24h. "
                "Cache invalidation strategy included. Complexity: medium (3).",
        "metadata": {"category":"pattern","complexity_band":3,"actual_hours":20,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_35",
        "text": "GDPR compliance module: consent management, data export, and right-to-be-forgotten: 32-48h. "
                "NFR with legal implications. Complexity: high (4).",
        "metadata": {"category":"pattern","complexity_band":4,"actual_hours":40,
                     "team_size":2,"fp_count":0},
    },
    {
        "id": "pattern_36",
        "text": "Sales pipeline with stage tracking, probability scores, and forecasting: 28-40h. "
                "CRM domain. Complexity: medium-high (3).",
        "metadata": {"category":"pattern","complexity_band":3,"actual_hours":34,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_37",
        "text": "Email automation with drip campaigns, open tracking, and unsubscribe: 32-48h. "
                "Third-party ESP integration. Complexity: high (4).",
        "metadata": {"category":"pattern","complexity_band":4,"actual_hours":40,
                     "team_size":1,"fp_count":0},
    },
    {
        "id": "pattern_38",
        "text": "Simple read-only data display widget (list, table, or card view): 4-8h. "
                "No business logic. Complexity: trivial (1).",
        "metadata": {"category":"pattern","complexity_band":1,"actual_hours":6,
                     "team_size":1,"fp_count":0},
    },
    # ── Category 4: Planning examples (few-shot context for PlannerAgent LLM) ──
    {
        "id": "plan_ex_01",
        "text": "clinic management system: patient registration, appointments, doctor consultation, billing, email reminders, security, performance",
        "metadata": {
            "category": "planning_example", "domain": "clinic",
            "critic_score": 0.92, "task_count": 8, "fp_count": 0,
            "example_tasks": (
                "Implement Patient Registration (FR, C3) | "
                "Implement Appointment Booking (FR, C3) | "
                "Implement Doctor Consultation View (FR, C2) | "
                "Implement Invoice Generation (FR, C3) | "
                "Implement Email Reminder Service (FR, C3) | "
                "Implement User Authentication (FR, C2) | "
                "System Performance NFR - 2s response (NFR, C3) | "
                "Data Security and Access Control NFR (NFR, C3)"
            ),
        },
    },
    {
        "id": "plan_ex_02",
        "text": "CRM system: lead tracking, email automation, pipeline view, contact management, sales reporting, role-based access",
        "metadata": {
            "category": "planning_example", "domain": "crm",
            "critic_score": 0.91, "task_count": 7, "fp_count": 0,
            "example_tasks": (
                "Implement Lead CRUD and Status Tracking (FR, C3) | "
                "Implement Email Automation Integration (FR, C4) | "
                "Implement Sales Pipeline Dashboard (FR, C3) | "
                "Implement Contact Search and Filter (FR, C2) | "
                "Implement Sales Reports and Export (FR, C3) | "
                "Role-Based Access Control NFR (NFR, C3) | "
                "System Uptime and Reliability NFR (NFR, C3)"
            ),
        },
    },
    {
        "id": "plan_ex_03",
        "text": "e-commerce platform: product catalog, shopping cart, payment gateway, order tracking, user reviews, inventory management",
        "metadata": {
            "category": "planning_example", "domain": "ecommerce",
            "critic_score": 0.89, "task_count": 9, "fp_count": 0,
            "example_tasks": (
                "Implement Product Catalog and Search (FR, C3) | "
                "Implement Shopping Cart and Checkout (FR, C3) | "
                "Implement Payment Gateway Integration (FR, C4) | "
                "Implement Order Tracking and History (FR, C3) | "
                "Implement User Reviews and Ratings (FR, C2) | "
                "Implement Inventory Management (FR, C3) | "
                "Implement User Registration and Auth (FR, C2) | "
                "Payment Security PCI-DSS Compliance NFR (NFR, C4) | "
                "Page Load Performance NFR (NFR, C3)"
            ),
        },
    },
    {
        "id": "plan_ex_04",
        "text": "HR system: employee profiles, leave management, payroll, attendance tracking, performance reviews, notifications",
        "metadata": {
            "category": "planning_example", "domain": "hr",
            "critic_score": 0.90, "task_count": 8, "fp_count": 0,
            "example_tasks": (
                "Implement Employee Profile Management (FR, C3) | "
                "Implement Leave Request and Approval (FR, C3) | "
                "Implement Payroll Calculation Module (FR, C4) | "
                "Implement Attendance Tracking (FR, C3) | "
                "Implement Performance Review Workflow (FR, C4) | "
                "Implement Email and Push Notifications (FR, C3) | "
                "Data Privacy and GDPR Compliance NFR (NFR, C4) | "
                "System Availability 99.9% SLA NFR (NFR, C3)"
            ),
        },
    },
    {
        "id": "plan_ex_05",
        "text": "LMS learning management system: course creation, quiz engine, student enrollment, progress tracking, certificates, video streaming",
        "metadata": {
            "category": "planning_example", "domain": "lms",
            "critic_score": 0.88, "task_count": 8, "fp_count": 0,
            "example_tasks": (
                "Implement Course Creation and Management (FR, C3) | "
                "Implement Quiz and Assessment Engine (FR, C4) | "
                "Implement Student Enrollment and Access (FR, C2) | "
                "Implement Progress Tracking Dashboard (FR, C3) | "
                "Implement Certificate Generation (FR, C3) | "
                "Implement Video Streaming Module (FR, C4) | "
                "System Scalability for Concurrent Users NFR (NFR, C4) | "
                "Accessibility WCAG 2.1 Compliance NFR (NFR, C3)"
            ),
        },
    },
    {
        "id": "plan_ex_06",
        "text": "IoT dashboard: sensor data ingestion, real-time monitoring, alert thresholds, device management, historical charts, API integration",
        "metadata": {
            "category": "planning_example", "domain": "iot",
            "critic_score": 0.87, "task_count": 8, "fp_count": 0,
            "example_tasks": (
                "Implement Sensor Data Ingestion Pipeline (FR, C4) | "
                "Implement Real-Time Monitoring Dashboard (FR, C4) | "
                "Implement Alert Threshold Configuration (FR, C3) | "
                "Implement Device Registry and Management (FR, C3) | "
                "Implement Historical Data Charts (FR, C3) | "
                "Implement External API Integration (FR, C4) | "
                "Data Throughput and Latency NFR (NFR, C4) | "
                "System Security and Device Auth NFR (NFR, C3)"
            ),
        },
    },
    {
        "id": "plan_ex_07",
        "text": "SaaS billing system: subscription plans, Stripe payment, invoice generation, usage tracking, dunning management, admin portal",
        "metadata": {
            "category": "planning_example", "domain": "fintech",
            "critic_score": 0.91, "task_count": 8, "fp_count": 0,
            "example_tasks": (
                "Implement Subscription Plan Management (FR, C3) | "
                "Implement Stripe Payment Integration (FR, C4) | "
                "Implement Invoice Generation and PDF Export (FR, C3) | "
                "Implement Usage Tracking and Metering (FR, C4) | "
                "Implement Failed Payment Dunning Flow (FR, C3) | "
                "Implement Admin Billing Portal (FR, C3) | "
                "PCI-DSS Payment Security Compliance NFR (NFR, C4) | "
                "99.99% Uptime SLA for Billing Service NFR (NFR, C4)"
            ),
        },
    },
    {
        "id": "plan_ex_08",
        "text": "university registration portal: course enrollment, schedule builder, fee payment, transcript requests, student portal, faculty management",
        "metadata": {
            "category": "planning_example", "domain": "education",
            "critic_score": 0.89, "task_count": 8, "fp_count": 0,
            "example_tasks": (
                "Implement Course Enrollment and Waitlist (FR, C3) | "
                "Implement Schedule Builder with Conflict Detection (FR, C4) | "
                "Implement Fee Payment Gateway (FR, C4) | "
                "Implement Transcript Request Workflow (FR, C3) | "
                "Implement Student Self-Service Portal (FR, C3) | "
                "Implement Faculty Load Management (FR, C3) | "
                "Multi-Language Support Arabic and English NFR (NFR, C3) | "
                "High Concurrency During Registration Period NFR (NFR, C4)"
            ),
        },
    },
    # -- Category 5: Curated task-level estimation patterns for RAG calibration --
    {
        "id": "est_pattern_01",
        "text": "Hospital patient triage workflow with priority scoring, nurse handoff, and audit log: 36-52h. "
                "Includes queue state changes and role-specific visibility. Type: FR. Complexity: high (4).",
        "metadata": {"category":"estimation_pattern","domain":"hospital","req_type":"FR",
                     "complexity_band":4,"actual_hours":44,"team_size":2,"fp_count":0,
                     "source_type":"curated_task_pattern"},
    },
    {
        "id": "est_pattern_02",
        "text": "LMS quiz authoring with question bank, timed attempts, auto-grading, and feedback rules: 34-50h. "
                "Business logic heavy feature. Type: FR. Complexity: high (4).",
        "metadata": {"category":"estimation_pattern","domain":"lms","req_type":"FR",
                     "complexity_band":4,"actual_hours":42,"team_size":2,"fp_count":0,
                     "source_type":"curated_task_pattern"},
    },
    {
        "id": "est_pattern_03",
        "text": "Fintech KYC review workflow with document upload, provider callback, status transitions, and manual override: 40-60h. "
                "External verification integration. Type: FR. Complexity: high (4).",
        "metadata": {"category":"estimation_pattern","domain":"fintech","req_type":"FR",
                     "complexity_band":4,"actual_hours":50,"team_size":2,"fp_count":0,
                     "source_type":"curated_task_pattern"},
    },
    {
        "id": "est_pattern_04",
        "text": "CRM lead scoring and sales forecast dashboard with weighted pipeline stages and export: 28-44h. "
                "Analytics and reporting workflow. Type: FR. Complexity: medium-high (3).",
        "metadata": {"category":"estimation_pattern","domain":"crm","req_type":"FR",
                     "complexity_band":3,"actual_hours":36,"team_size":1,"fp_count":0,
                     "source_type":"curated_task_pattern"},
    },
    {
        "id": "est_pattern_05",
        "text": "IoT alert rules engine with threshold configuration, deduplication, and notification routing: 32-48h. "
                "Real-time event workflow. Type: FR. Complexity: high (4).",
        "metadata": {"category":"estimation_pattern","domain":"iot","req_type":"FR",
                     "complexity_band":4,"actual_hours":40,"team_size":2,"fp_count":0,
                     "source_type":"curated_task_pattern"},
    },
    {
        "id": "est_pattern_06",
        "text": "University schedule conflict detection with prerequisites, capacity limits, and waitlist validation: 36-56h. "
                "Enrollment business rules. Type: FR. Complexity: high (4).",
        "metadata": {"category":"estimation_pattern","domain":"education","req_type":"FR",
                     "complexity_band":4,"actual_hours":46,"team_size":2,"fp_count":0,
                     "source_type":"curated_task_pattern"},
    },
    {
        "id": "est_pattern_07",
        "text": "HIPAA audit trail and PHI access monitoring with exportable compliance logs: 34-54h. "
                "Security and compliance NFR. Type: NFR. Complexity: high (4).",
        "metadata": {"category":"estimation_pattern","domain":"hospital","req_type":"NFR",
                     "complexity_band":4,"actual_hours":44,"team_size":2,"fp_count":0,
                     "source_type":"curated_task_pattern"},
    },
    {
        "id": "est_pattern_08",
        "text": "Billing service availability hardening with health checks, retry policy, and failover runbook: 40-64h. "
                "Reliability NFR. Type: NFR. Complexity: high (4).",
        "metadata": {"category":"estimation_pattern","domain":"fintech","req_type":"NFR",
                     "complexity_band":4,"actual_hours":52,"team_size":2,"fp_count":0,
                     "source_type":"curated_task_pattern"},
    },
    # -- Category 6: Curated planning examples for LLM-guided decomposition --
    {
        "id": "plan_ex_09",
        "text": "hospital operations platform: triage, appointments, EHR access, lab orders, discharge summary, HIPAA audit logging",
        "metadata": {
            "category": "planning_example", "domain": "hospital",
            "critic_score": 0.93, "task_count": 8, "fp_count": 0,
            "source_type": "curated_planning_example",
            "example_tasks": (
                "Implement Patient Triage Queue (FR, C4) | "
                "Implement Appointment Scheduling (FR, C3) | "
                "Implement EHR Patient Record Access (FR, C4) | "
                "Implement Lab Order Workflow (FR, C4) | "
                "Implement Discharge Summary Generation (FR, C3) | "
                "Implement Role-Based Clinical Access (FR, C4) | "
                "HIPAA Audit Trail NFR (NFR, C4) | "
                "Clinical Data Availability NFR (NFR, C4)"
            ),
        },
    },
    {
        "id": "plan_ex_10",
        "text": "advanced LMS platform: course builder, quiz bank, progress analytics, certificate verification, video lessons, accessibility",
        "metadata": {
            "category": "planning_example", "domain": "lms",
            "critic_score": 0.91, "task_count": 8, "fp_count": 0,
            "source_type": "curated_planning_example",
            "example_tasks": (
                "Implement Course Builder (FR, C3) | "
                "Implement Quiz Question Bank (FR, C4) | "
                "Implement Student Progress Analytics (FR, C3) | "
                "Implement Certificate Verification (FR, C3) | "
                "Implement Video Lesson Playback (FR, C4) | "
                "Implement Instructor Feedback Workflow (FR, C3) | "
                "Accessibility WCAG Compliance NFR (NFR, C3) | "
                "Concurrent Learner Scalability NFR (NFR, C4)"
            ),
        },
    },
    {
        "id": "plan_ex_11",
        "text": "fintech onboarding and payment platform: KYC, wallet funding, payment gateway, fraud review, settlement reports, PCI controls",
        "metadata": {
            "category": "planning_example", "domain": "fintech",
            "critic_score": 0.92, "task_count": 8, "fp_count": 0,
            "source_type": "curated_planning_example",
            "example_tasks": (
                "Implement KYC Verification Workflow (FR, C4) | "
                "Implement Wallet Funding Flow (FR, C4) | "
                "Integrate Payment Gateway (FR, C4) | "
                "Implement Fraud Review Queue (FR, C4) | "
                "Implement Settlement Reporting (FR, C3) | "
                "Implement Customer Notification Events (FR, C3) | "
                "PCI-DSS Security Controls NFR (NFR, C5) | "
                "Payment Service Availability NFR (NFR, C4)"
            ),
        },
    },
    {
        "id": "plan_ex_12",
        "text": "CRM revenue operations platform: lead capture, pipeline stages, email campaigns, activity timeline, forecast dashboard, RBAC",
        "metadata": {
            "category": "planning_example", "domain": "crm",
            "critic_score": 0.90, "task_count": 7, "fp_count": 0,
            "source_type": "curated_planning_example",
            "example_tasks": (
                "Implement Lead Capture and Deduplication (FR, C3) | "
                "Implement Sales Pipeline Stages (FR, C3) | "
                "Integrate Email Campaign Events (FR, C4) | "
                "Implement Account Activity Timeline (FR, C3) | "
                "Implement Revenue Forecast Dashboard (FR, C3) | "
                "Role-Based Sales Access NFR (NFR, C3) | "
                "CRM Reporting Performance NFR (NFR, C3)"
            ),
        },
    },
    {
        "id": "plan_ex_13",
        "text": "IoT monitoring platform: device registry, MQTT ingestion, real-time dashboard, alert policies, historical trends, device auth",
        "metadata": {
            "category": "planning_example", "domain": "iot",
            "critic_score": 0.90, "task_count": 8, "fp_count": 0,
            "source_type": "curated_planning_example",
            "example_tasks": (
                "Implement Device Registry (FR, C3) | "
                "Implement MQTT Data Ingestion (FR, C4) | "
                "Implement Real-Time Sensor Dashboard (FR, C4) | "
                "Implement Alert Policy Engine (FR, C4) | "
                "Implement Historical Trend Charts (FR, C3) | "
                "Implement Device Authentication (FR, C3) | "
                "Telemetry Throughput NFR (NFR, C4) | "
                "Sensor Data Retention NFR (NFR, C3)"
            ),
        },
    },
    {
        "id": "plan_ex_14",
        "text": "university student services portal: enrollment, schedule conflict detection, tuition payment, transcript requests, advisor approvals, bilingual UI",
        "metadata": {
            "category": "planning_example", "domain": "education",
            "critic_score": 0.91, "task_count": 8, "fp_count": 0,
            "source_type": "curated_planning_example",
            "example_tasks": (
                "Implement Course Enrollment (FR, C3) | "
                "Implement Schedule Conflict Detection (FR, C4) | "
                "Integrate Tuition Payment Gateway (FR, C4) | "
                "Implement Transcript Request Workflow (FR, C3) | "
                "Implement Advisor Approval Workflow (FR, C3) | "
                "Implement Student Notification Center (FR, C3) | "
                "Arabic and English Localization NFR (NFR, C3) | "
                "Registration Peak Load NFR (NFR, C4)"
            ),
        },
    },
]


def seed_kb(kb: KnowledgeBase) -> int:
    """Seed the knowledge base with estimation-focused documents."""
    kb.add_documents(ESTIMATION_DOCS)
    print(f"[KB] Seeded {len(ESTIMATION_DOCS)} estimation documents.")
    return len(ESTIMATION_DOCS)


def seed_knowledge_base(reset: bool = False) -> KnowledgeBase:
    """Create and seed the default KnowledgeBase collection."""
    kb = KnowledgeBase()
    if reset:
        try:
            kb.client.delete_collection("pm_knowledge")
        except Exception:  # noqa: BLE001
            pass
        kb.collection = kb.client.get_or_create_collection("pm_knowledge")
    seed_kb(kb)
    print(f"Total docs: {kb.count()}")
    return kb
