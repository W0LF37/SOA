# Requirements Template

Use this template to write your project requirements in a structured way.
Each requirement block must start with `[REQ-NN]`, where `NN` is a zero-padded number such as `01`, `02`, or `03`.
Write one requirement per block, and keep the description clear and specific.
Repeat the same field structure for every requirement you add.

## Required Block Format

```text
[REQ-01]
Type:        Functional | Non-Functional
Description: <one clear sentence describing what the system must do>
Actor:       <who uses or triggers this - e.g. Doctor, Admin, System>
Priority:    High | Medium | Low
Notes:       <optional - any clarification or edge case>
```

## Worked Example

```text
[REQ-01]
Type:        Functional
Description: The system must allow reception staff to register a new patient using name, phone number, and national ID.
Actor:       Receptionist
Priority:    High
Notes:       Prevent duplicate registration when the same national ID already exists.
```

## Important Note

`Description` is mandatory. All other fields are optional but recommended.
