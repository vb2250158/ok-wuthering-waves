# Daily activity OCR correction

This local fork distinguishes unreadable activity from a real zero. DailyTask reads a bounded numeric region, retries at most three times, and raises rather than executing follow-up actions based on a fabricated zero. Stamina progress is logged separately from daily activity.

The focused source-method tests cover zero, values above the reward threshold, transient empty output, invalid strings, and conflicting numbers. They do not establish the cause of any particular transient capture failure or prove a live game reward result.

Version: local activity OCR correction 2026-10-18. No upstream pull request is created.
