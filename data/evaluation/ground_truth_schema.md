# Ground Truth Entry Schema

Each ground truth entry describes one evaluation sample and the minimum quality expectations for its planner output.

```json
{
  "sample_id": "S01",
  "description": "One sentence describing what this sample tests",
  "input_file": "relative/path/to/input.txt",
  "expected": {
    "task_count_min": 5,
    "task_count_max": 15,
    "fr_count_min": 4,
    "nfr_count_min": 0,
    "optional_count_min": 0,
    "has_dependency_chain": true,
    "critical_path_min_length": 2,
    "forbidden_title_substrings": ["Actor:", "system must"]
  }
}
```

Field meanings:

- `sample_id`: unique sample identifier such as `S01`
- `description`: one sentence describing the scenario being evaluated
- `input_file`: relative path to the sample input file
- `expected.task_count_min`: minimum acceptable number of tasks
- `expected.task_count_max`: maximum acceptable number of tasks
- `expected.fr_count_min`: minimum number of FR tasks expected
- `expected.nfr_count_min`: minimum number of NFR tasks expected
- `expected.optional_count_min`: minimum number of optional or low-confidence tasks expected
- `expected.has_dependency_chain`: whether at least one task must have non-empty dependencies
- `expected.critical_path_min_length`: minimum acceptable critical path hop count
- `expected.forbidden_title_substrings`: substrings that must not appear in any generated task title
