# Original annotation tool with audit extension

Base: `technical_evaluation/annotation/annotation_tool/Simret/annotation_tool.html` (blue original UI). Its original CSS and core annotation layout are reused without redesign. The audit extension adds current-step comparison, original-evidence highlights, revised-copy persistence, reviewer/reason metadata, provenance, and JSON export with a selectable-text fallback.

URL: http://127.0.0.1:8769/original-audit/

Original labels are read-only references. The right-hand annotation controls edit a separate copy of Simret's 48 records. Original source files and original annotation-tool storage are not overwritten. Yukun is represented only on the original assignment using the corresponding golden entries as previously confirmed by the user. Other golden records are explicitly labeled final adjudications, not independent Yukun annotations.

Edits auto-save to local browser storage. Fill reviewer and case-specific rationale before exporting modified cases. `Export revised JSON` includes revisions and audit history. Original PARTIAL/clear controls are preserved; those values are not binary final labels for downstream evaluation.

The prior custom audit page's saved revisions are migrated when opening this tool for the first time in the same browser/origin. The previous page remains intact. Future changes on the two pages are not synchronized; use this tool thereafter. Export a backup before changing browsers or rebuilding inputs. `?test=1` uses separate test storage.

Build with `python3 -B technical_evaluation/annotation/verdict_review/build_original_audit.py` from the EvalAgent repository. No public hosting: data is embedded in the HTML.

Verified: original verdict controls, original-step navigation, source-specific literal highlights, revised48 JSON payload with reviewer/history, and no browser console errors during testing. These are post-review annotations and must not be described as independent original annotator responses.
