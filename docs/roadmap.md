# Roadmap

## M0: Executable Foundation

Status: implemented.

Deliverables:

- schema v0.1
- staging importer
- synthetic fixtures
- CBC normalization and CTCAE grading
- trend engine
- baseline candidate action rules
- safety critic seed rules
- evaluation metrics
- Codex context CLI/API
- doctor-gold reasoning reconstruction CLI/API

## M1: CBC Deterministic Reliability

Next:

- tighten CBC action rule pack
- use doctor reconstruction exclusions to reduce Hb-low false-positive action labels
- separate `missing_context` scoring from action scoring in reports
- add more boundary tests for WBC-low/ANC-normal and Hb-low/no-action cases
- add report-level validation errors for missing key CBC fields

## M2: Evaluation And Safety

Next:

- convert all owner-reviewed cases into structured gold reasoning atoms
- improve atom matching with numeric tolerance and structured trend atoms
- add full 15-case safety red-team pass/fail report

## M3: Private Case Memory

Next:

- append-only case memory format
- doctor review ingestion
- learning-layer labels for extraction/schema/grading/trend/action/safety errors

## M4: Public Knowledge/RAG

Next:

- connect to existing CSCO RAG rather than creating a new retrieval stack
- expose retrieved evidence through the same context bundle
