# RSI evaluation notes

## Current micro-benchmark

`benchmark.py` measures whether a retrieval policy places the one intended experience for each synthetic recurring task in its top results. The 20 records and 20 queries were hand-authored to cover different engineering domains.

Compared methods:

- `no_recall`: no experience is supplied;
- `recency_top3`: always supply the three newest records;
- `lesson_only_overlap`: Jaccard overlap over unstructured lesson, anti-pattern, and evidence text;
- `rsi_structured`: the bundled weighted-field RSI retriever.

Metrics are Recall@1, Recall@3, and mean reciprocal rank. A paired bootstrap interval compares RSI and recency Recall@3 with 10,000 samples and seed `20260904`.

Run from the repository root:

```bash
python3 experiments/benchmark.py --output experiments/results/latest.json
```

The dataset is intentionally small and synthetic. Its purpose is regression testing and falsifiable documentation, not a claim about downstream agent quality.

## Recommended end-to-end experiment

Use at least 30 pairs of tasks where the second task benefits from a non-obvious lesson learned during the first.

1. Freeze the model, prompt outside RSI, temperature, tool permissions, repository state, and token/time budget.
2. On task A, let the RSI condition propose experience and use a human-approved, blinded gold record. Do not expose it to the control condition.
3. On task B, randomly assign `control` (no stored experience) or `RSI recall`; rotate assignment across matched pairs.
4. Hide condition labels from evaluators. Prefer executable tests and task-specific rubrics over style judgments.
5. Record pass/fail, recurrence of the original error, irrelevant-experience application, token usage, elapsed time, and approval burden.
6. Report all exclusions, prompt versions, raw task IDs, and confidence intervals. Treat multiple runs of the same task as clustered observations.

Primary outcomes should be task-B pass rate and repeated-error rate. Safety outcomes should include secret-rejection recall, unapproved-write count, stale-experience misuse, and cross-scope preference leakage.

Do not tune the retriever on the held-out task-B prompts. Keep a development split for ranking changes and rerun the hidden evaluation only after freezing the implementation.
