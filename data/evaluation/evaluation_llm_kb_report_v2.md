# Planner Agent Evaluation Report

**Date:** 2026-04-28 20:05:32 UTC  
**Mode:** llm_with_kb  
**Fallback rate:** 65%

## Summary

| Metric | Value |
|---|---|
| Overall result | **FAIL 18/20 samples passed** |
| Pass rate | 90.0% |
| Avg task count | 7.95 |
| Successful run rate | 100.0% |
| Direct generation rate | 35.0% |
| Avg critic score | 0.986 |

## Training Decision Gate

| Check | Expected | Actual | Result |
|---|---|---|---|
| `fallback_rate_pct` | <= 30.0 | 65.0 | **FAIL** |
| `direct_generation_rate_pct` | >= 70.0 | 35.0 | **FAIL** |
| `average_critic_score` | >= 0.85 | 0.986 | **OK** |
| `average_overall_score` | >= 0.78 | 0.764 | **FAIL** |

**Training recommended:** YES


## Check Pass Rates

| Check | Pass Rate |
|---|---|
| `task_count_in_range` | ########## 100% |
| `fr_count_min` | ########## 100% |
| `nfr_count_min` | ########## 100% |
| `optional_count_min` | ########## 100% |
| `forbidden_title_substrings` | ########## 100% |
| `requirement_coverage` | ########## 100% |
| `has_dependency_chain` | ########-- 80% |
| `critical_path_min_length` | ########-- 80% |

## Sample Results

### [PASS] S01 -- Clinic brief — baseline hospital sample (brief format)

**Input:** `data/raw/docs/project_brief_sample.txt`  
**Tasks:** 11 (FR: 7 | NFR: 4 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 7:4  
Task count in expected range (4-20): Yes  
Critic: approved (1.000)  
**Fallback:** used (Rule-based fallback was used after LLM planning failed: ValueError: Quality check failed: decomposition produced fewer tasks than requirements: 3 < 9; decomposition under-produced tasks for REQ-02: expected at least 2, got 1; decomposition under-produced tasks for REQ-04: expected at least 2, got 0)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 4-20 | 11 |
| `fr_count_min` | **OK** | >= 4 | 7 |
| `nfr_count_min` | **OK** | >= 1 | 4 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 70% | 100% (9/9) |

### [PASS] S02 -- Structured template sample - user account management with NFR constraints

**Input:** `data/raw/docs/requirements_template_sample.txt`  
**Tasks:** 6 (FR: 3 | NFR: 3 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 3:3  
Task count in expected range (5-10): Yes  
Critic: approved (1.000)  
**Fallback:** used (Rule-based fallback was used after LLM planning failed: ValueError: Quality check failed: decomposition produced fewer tasks than requirements: 2 < 5; decomposition under-produced tasks for REQ-05: expected at least 2, got 0)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 5-10 | 6 |
| `fr_count_min` | **OK** | >= 3 | 3 |
| `nfr_count_min` | **OK** | >= 2 | 3 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 80% | 100% (5/5) |

### [PASS] S03 -- Single-requirement input — planner must produce at least one task

**Input:** `data/evaluation/sample_single.txt`  
**Tasks:** 1 (FR: 1 | NFR: 0 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 1:0  
Task count in expected range (1-3): Yes  
Critic: approved (0.990)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 1-3 | 1 |
| `fr_count_min` | **OK** | >= 1 | 1 |
| `nfr_count_min` | **OK** | >= 0 | 0 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `has_dependency_chain` | **OK** | False | False |
| `critical_path_min_length` | **OK** | >= 1 | 1 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 80% | 100% (1/1) |

### [PASS] S04 -- Project brief format — clinic system with 5 features and NFR constraints

**Input:** `data/raw/docs/project_brief_sample.txt`  
**Tasks:** 11 (FR: 7 | NFR: 4 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 7:4  
Task count in expected range (4-14): Yes  
Critic: approved (1.000)  
**Fallback:** used (Rule-based fallback was used after LLM planning failed: ValueError: Quality check failed: decomposition produced fewer tasks than requirements: 3 < 9; decomposition under-produced tasks for REQ-02: expected at least 2, got 1; decomposition under-produced tasks for REQ-04: expected at least 2, got 0)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 4-14 | 11 |
| `fr_count_min` | **OK** | >= 4 | 7 |
| `nfr_count_min` | **OK** | >= 1 | 4 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `has_dependency_chain` | **OK** | True | True |
| `critical_path_min_length` | **OK** | >= 2 | 4 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 80% | 100% (9/9) |

### [PASS] S05 -- Hard project brief — university portal with 8 features, 4 actors, optional scope, and 6 NFRs

**Input:** `data/raw/docs/project_brief_hard.txt`  
**Tasks:** 16 (FR: 10 | NFR: 6 | Optional: 2)  
**Task Quality**  
FR:NFR ratio: 10:6  
Task count in expected range (8-22): Yes  
Critic: approved (1.000)  
**Fallback:** used (Rule-based fallback was used after LLM planning failed: ValueError: Quality check failed: decomposition produced fewer tasks than requirements: 9 < 14; decomposition under-produced tasks for REQ-01: expected at least 2, got 1)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 8-22 | 16 |
| `fr_count_min` | **OK** | >= 6 | 10 |
| `nfr_count_min` | **OK** | >= 3 | 6 |
| `optional_count_min` | **OK** | >= 1 | 2 |
| `has_dependency_chain` | **OK** | True | True |
| `critical_path_min_length` | **OK** | >= 2 | 3 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 80% | 100% (14/14) |

### [PASS] S06 -- E-commerce project brief

**Input:** `data/raw/docs/project_brief_ecommerce.txt`  
**Tasks:** 14 (FR: 9 | NFR: 5 | Optional: 1)  
**Task Quality**  
FR:NFR ratio: 9:5  
Task count in expected range (10-25): Yes  
Critic: approved (0.950)  
**Fallback:** used (Rule-based fallback was used after LLM planning failed: ValueError: Quality check failed: decomposition produced fewer tasks than requirements: 2 < 13; decomposition under-produced tasks for REQ-07: expected at least 2, got 0)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 10-25 | 14 |
| `fr_count_min` | **OK** | >= 7 | 9 |
| `nfr_count_min` | **OK** | >= 3 | 5 |
| `optional_count_min` | **OK** | >= 1 | 1 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 75% | 100% (13/13) |

### [PASS] S07 -- Library management system brief

**Input:** `data/raw/docs/project_brief_library.txt`  
**Tasks:** 9 (FR: 6 | NFR: 3 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 6:3  
Task count in expected range (6-18): Yes  
Critic: approved (1.000)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 6-18 | 9 |
| `fr_count_min` | **OK** | >= 5 | 6 |
| `nfr_count_min` | **OK** | >= 2 | 3 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 75% | 100% (9/9) |

### [PASS] S08 -- Single NFR — system availability requirement

**Input:** `<inline>`  
**Tasks:** 1 (FR: 0 | NFR: 1 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 0:1  
Task count in expected range (1-4): Yes  
Critic: approved (0.890)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 1-4 | 1 |
| `fr_count_min` | **OK** | >= 0 | 0 |
| `nfr_count_min` | **OK** | >= 1 | 1 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 80% | 100% (1/1) |

### [PASS] S09 -- HR management system — leave, payroll, recruitment

**Input:** `data/raw/docs/project_brief_hr_system.txt`  
**Tasks:** 12 (FR: 8 | NFR: 4 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 8:4  
Task count in expected range (7-18): Yes  
Critic: approved (1.000)  
**Fallback:** used (Rule-based fallback was used after LLM planning failed: ValueError: Quality check failed: complexity out of range at T012: expected ~4, got 2)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 7-18 | 12 |
| `fr_count_min` | **OK** | >= 5 | 8 |
| `nfr_count_min` | **OK** | >= 2 | 4 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `has_dependency_chain` | **OK** | True | True |
| `critical_path_min_length` | **OK** | >= 2 | 2 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 75% | 100% (10/10) |

### [PASS] S10 -- Fintech payment gateway with KYC and PCI-DSS compliance

**Input:** `data/raw/docs/project_brief_fintech.txt`  
**Tasks:** 10 (FR: 6 | NFR: 4 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 6:4  
Task count in expected range (6-16): Yes  
Critic: approved (1.000)  
**Fallback:** used (Rule-based fallback was used after LLM planning failed: ValueError: Quality check failed: req_type mismatch at T001: expected NFR, got FR; decomposition produced fewer tasks than requirements: 9 < 10)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 6-16 | 10 |
| `fr_count_min` | **OK** | >= 4 | 6 |
| `nfr_count_min` | **OK** | >= 3 | 4 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `has_dependency_chain` | **OK** | True | True |
| `critical_path_min_length` | **OK** | >= 2 | 2 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 75% | 100% (10/10) |

### [PASS] S11 -- IoT sensor monitoring dashboard with real-time alerting

**Input:** `data/raw/docs/project_brief_iot_dashboard.txt`  
**Tasks:** 10 (FR: 7 | NFR: 3 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 7:3  
Task count in expected range (6-16): Yes  
Critic: approved (1.000)  
**Fallback:** used (Rule-based fallback was used after LLM planning failed: ValueError: Quality check failed: decomposition produced fewer tasks than requirements: 3 < 10)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 6-16 | 10 |
| `fr_count_min` | **OK** | >= 4 | 7 |
| `nfr_count_min` | **OK** | >= 3 | 3 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `has_dependency_chain` | **OK** | True | True |
| `critical_path_min_length` | **OK** | >= 2 | 2 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 75% | 100% (10/10) |

### [PASS] S12 -- Learning Management System with quiz engine and certificates

**Input:** `data/raw/docs/project_brief_lms.txt`  
**Tasks:** 10 (FR: 8 | NFR: 2 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 8:2  
Task count in expected range (7-18): Yes  
Critic: approved (1.000)  
**Fallback:** used (Rule-based fallback was used after LLM planning failed: ValueError: Quality check failed: req_type mismatch at T009: expected FR, got NFR)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 7-18 | 10 |
| `fr_count_min` | **OK** | >= 5 | 8 |
| `nfr_count_min` | **OK** | >= 2 | 2 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `has_dependency_chain` | **OK** | True | True |
| `critical_path_min_length` | **OK** | >= 2 | 3 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 75% | 100% (10/10) |

### [PASS] S13 -- CRM platform with sales pipeline and email automation

**Input:** `data/raw/docs/project_brief_crm.txt`  
**Tasks:** 11 (FR: 8 | NFR: 3 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 8:3  
Task count in expected range (7-18): Yes  
Critic: approved (1.000)  
**Fallback:** used (Rule-based fallback was used after LLM planning failed: ValidationError: 2 validation errors for TaskList
tasks.10.req_type
  Field required [type=missing, input_value={'id': 'T011', 'title': '...10', 'dependencies': []}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
tasks.10.complexity
  Field required [type=missing, input_value={'id': 'T011', 'title': '...10', 'dependencies': []}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 7-18 | 11 |
| `fr_count_min` | **OK** | >= 5 | 8 |
| `nfr_count_min` | **OK** | >= 2 | 3 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `has_dependency_chain` | **OK** | True | True |
| `critical_path_min_length` | **OK** | >= 2 | 2 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 75% | 100% (10/10) |

### [FAIL] S14 -- SaaS subscription billing with dunning and revenue reporting

**Input:** `data/raw/docs/project_brief_saas_billing.txt`  
**Tasks:** 10 (FR: 8 | NFR: 2 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 8:2  
Task count in expected range (7-16): Yes  
Critic: approved (1.000)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 7-16 | 10 |
| `fr_count_min` | **OK** | >= 5 | 8 |
| `nfr_count_min` | **OK** | >= 2 | 2 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `has_dependency_chain` | **FAIL** | True | False |
| `critical_path_min_length` | **FAIL** | >= 2 | 1 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 75% | 100% (10/10) |

### [FAIL] S15 -- Social networking platform with feed and moderation

**Input:** `data/raw/docs/project_brief_social_platform.txt`  
**Tasks:** 10 (FR: 7 | NFR: 3 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 7:3  
Task count in expected range (7-18): Yes  
Critic: approved (1.000)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 7-18 | 10 |
| `fr_count_min` | **OK** | >= 5 | 7 |
| `nfr_count_min` | **OK** | >= 2 | 3 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `has_dependency_chain` | **FAIL** | True | False |
| `critical_path_min_length` | **FAIL** | >= 2 | 1 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 75% | 100% (10/10) |

### [PASS] S16 -- Edge case: complex NFR with implied sub-tasks (scalability + caching)

**Input:** `<inline>`  
**Tasks:** 1 (FR: 0 | NFR: 1 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 0:1  
Task count in expected range (1-5): Yes  
Critic: approved (0.890)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 1-5 | 1 |
| `fr_count_min` | **OK** | >= 0 | 0 |
| `nfr_count_min` | **OK** | >= 1 | 1 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 70% | 100% (1/1) |

### [PASS] S17 -- Edge case: minimal MVP (3-sentence brief)

**Input:** `<inline>`  
**Tasks:** 3 (FR: 3 | NFR: 0 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 3:0  
Task count in expected range (2-8): Yes  
Critic: approved (1.000)  
**Fallback:** used (Rule-based fallback was used after LLM planning failed: ValueError: Quality check failed: req_type mismatch at T003: expected FR, got NFR)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 2-8 | 3 |
| `fr_count_min` | **OK** | >= 2 | 3 |
| `nfr_count_min` | **OK** | >= 0 | 0 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 70% | 100% (3/3) |

### [PASS] S18 -- Edge case: numbered list format requirements

**Input:** `<inline>`  
**Tasks:** 5 (FR: 3 | NFR: 2 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 3:2  
Task count in expected range (3-8): Yes  
Critic: approved (1.000)  
**Fallback:** used (Rule-based fallback was used after LLM planning failed: ValueError: Quality check failed: decomposition produced fewer tasks than requirements: 3 < 5)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 3-8 | 5 |
| `fr_count_min` | **OK** | >= 2 | 3 |
| `nfr_count_min` | **OK** | >= 1 | 2 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 70% | 100% (5/5) |

### [PASS] S19 -- Edge case: medical domain jargon (EHR system)

**Input:** `<inline>`  
**Tasks:** 5 (FR: 3 | NFR: 2 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 3:2  
Task count in expected range (3-10): Yes  
Critic: approved (1.000)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 3-10 | 5 |
| `fr_count_min` | **OK** | >= 2 | 3 |
| `nfr_count_min` | **OK** | >= 1 | 2 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 70% | 100% (5/5) |

### [PASS] S20 -- Edge case: contradictory requirements (fast + heavy analytics)

**Input:** `<inline>`  
**Tasks:** 3 (FR: 2 | NFR: 1 | Optional: 0)  
**Task Quality**  
FR:NFR ratio: 2:1  
Task count in expected range (2-8): Yes  
Critic: approved (1.000)  
**Fallback:** used (Rule-based fallback was used after LLM planning failed: ValueError: Quality check failed: req_type mismatch at T003: expected FR, got NFR)  

| Check | Result | Expected | Actual |
|---|---|---|---|
| `task_count_in_range` | **OK** | 2-8 | 3 |
| `fr_count_min` | **OK** | >= 1 | 2 |
| `nfr_count_min` | **OK** | >= 1 | 1 |
| `optional_count_min` | **OK** | >= 0 | 0 |
| `forbidden_title_substrings` | **OK** | no forbidden substrings in titles | clean |
| `requirement_coverage` | **OK** | >= 60% | 100% (3/3) |

## Failure Analysis

| Sample | Check | Expected | Actual |
|---|---|---|---|
| `S14` | `has_dependency_chain` | True | False |
| `S14` | `critical_path_min_length` | >= 2 | 1 |
| `S15` | `has_dependency_chain` | True | False |
| `S15` | `critical_path_min_length` | >= 2 | 1 |

Generated by AI Project Manager Planner Evaluation — rule_based_forced mode