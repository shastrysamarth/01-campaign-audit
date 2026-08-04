# CharacterQuilt technical screen: audit a campaign you cannot check by hand

Read [TASK.md](TASK.md) — it has the whole assignment.

## Setup

Python 3.11 or newer. Nothing to install.

## Commands

```bash
make demo   # run the customer's request and print the result
make test   # run the visible test
```

## Files

- `TASK.md` — the assignment.
- `fixtures/request.json` — the customer's request.
- `fixtures/target_accounts.json` — the list they uploaded (217 rows).
- `fixtures/customer_report.txt` — what they told support afterwards.
- `fixtures/failure-traces.jsonl` — events recorded during the run.
- `src/repair_lab.py` — the starter implementation.
- `tests/test_visible.py` — one visible test, not a full specification.
- `demo.py` — what `make demo` runs.
- `DECISIONS.md`, `SUBMISSION.md` — fill these in before you send the packet
  back.
