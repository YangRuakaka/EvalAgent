# Final-verdict review tool

Open `index.html` in a browser. It is self-contained and makes no network calls.
Alternatively serve this folder only: `python3 -m http.server 8769 --bind 127.0.0.1`.

- Includes 72 cases with task, criterion, original trajectory text and source annotations.
- Default filter shows any Dan/Simret/Golden verdict disagreement. Pair filters count only cases with both labels.
- Original labels remain read-only. Save a separate `pass`, `fail` or `needs_discussion` review with a required reason.
- Drafts and saved reviews use browser local storage keyed to the input dataset fingerprint. Export JSON for backup or transfer.
- Imported records must match the dataset. The app asks before replacing same-case reviews and retains previous saved reviews in history.
- Optional label hiding supports reviewing the task and trajectory before revealing source judgments.
- Evidence is context only; this tool does not alter or recompute evidence metrics.
- Golden is the final reference, not an independent third annotation. Original Yukun assignments are identified separately.
- The old 33-case set is not included: Dan/Simret source annotations for it were not established in this audit.

Rebuild with `python3 -B build_review.py`. This uses the existing metric report's golden path, the checked-in Dan export and the user-confirmed Simret export in Downloads. `index.html` does not require those files after building. The template contains only app code; generated `index.html` contains the research data, so do not publish it publicly without deciding to share that data.
