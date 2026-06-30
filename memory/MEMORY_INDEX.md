# Memory Index

Use this file as the first stop when resuming the project in a new Codex
conversation.

## Read Order

1. `PROJECT_CONTEXT.md` - compact project state and architecture.
2. `PROJECT_RULES.md` - critical behavior and data-format rules.
3. `NEXT_STEPS.md` - current work queue and immediate implementation target.
4. `DECISIONS.md` - durable design decisions already made.

## Detailed References

- `README.md` - full user-facing project documentation.
- `NEXT_STEPS.md` and `DECISIONS.md` - visual selector direction and design
  choices.

## Memory Policy

- Keep each memory file under 200 lines.
- Store stable facts, decisions, current state, and next actions.
- Do not store secrets, credentials, private keys, or API tokens.
- Store paths or setup notes instead of sensitive values.
- Remove or update stale entries when the implementation changes.
- At the end of a substantial task, update `NEXT_STEPS.md` and, if needed,
  `DECISIONS.md`.

## Quick Resume Prompt

```text
Read memory/MEMORY_INDEX.md first, then follow its read order. Use README.md
and the other memory files as references when needed.
```
