# Confirm saved accounts before DailyTask

The normal MultiAccountDailyTask previously ran the current client before reading
its saved-login identity. A failed first DailyTask therefore left both actions and
their account attribution unknown. Normal daily mode now requires an explicit,
ordered `Saved Accounts` list in the official `MultiAccountDailyTask` config.

```json
{
  "Saved Accounts": ["first****@example.test", "second****@example.test"]
}
```

Use the labels actually displayed by the saved-login selector. These labels are
selection requests, never proof of the current account. Empty, malformed or
colliding labels stop before game input. No passwords, tokens or verification
codes belong in this setting. Existing settings such as exit-after-task remain
unchanged.

For each configured account, including the first, the task uses the existing
native ComboBox or OCR selection flow. It rereads the selected field after the
settling interval, requires a recognized login confirmation, and waits for the
existing official world-entry check. Only then may DailyTask run. The returned
identity comes from the displayed saved-login field. Accounts outside the list
are never run, and a failed daily does not mark the account complete or continue
to the next one.

When starting at a saved-login page, the task selects there directly. When already
in the world, it uses the existing return-to-login flow. An unknown initial screen,
missing account, ambiguous selection, changed selection, unrecognized login button,
or incomplete login stops before DailyTask with an explicit reason. Cancellation
propagates. The task does not enter credentials or use an unrecognized coordinate
fallback to get past a prompt.

The three existing inspection-only modes require exactly one
`Daily Progress Inspection Account` and use the same first-account selection.
They never log into other saved accounts while searching for the target. Missing,
invalid or ambiguous targets and conflicting inspection modes stop before daily
actions. An empty target no longer means inspect all saved accounts. Inspection
does not alter DailyTask's farming/reward decisions or enable farming.

This is a source candidate for account-scoped inspection, not a Manager admission
or an installation approval. World entry can invoke the existing monthly-card
free-reward handler, so "inspection" does not promise zero game-state changes.
Only the native inspection bodies avoid farming and claim/purchase buttons.

For an external orchestrator, project the authorized frozen account list into this
official config in the original order. Preserve the original bytes and file/field
existence for recovery, then restore only the projected fields after confirmed
process exit, retaining other legitimate upstream writes. If the file originally
did not exist but upstream added other fields, do not delete those fields.
Do not substitute a target label for the observed identity, auto-populate the list
from every saved login, or clear failure results. An orchestrator which does not
yet project this field must keep the candidate disabled; missing scope fails closed.

Validation is synthetic and offline: `TestFirstAccountConfirmation.py` executes the
real method AST while replacing OS/UI responses, and `TestScheduleSupport.py`
checks the existing scheduling flow. No real login, account selection, farming,
reward verification or installed acceptance is claimed by these tests.
