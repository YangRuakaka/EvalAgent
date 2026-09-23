# Simret evidence audit

Open http://127.0.0.1:8769/simret/ while the local review server runs, or open `index.html` in a browser. All assets and data are embedded; do not publicly host this annotation data.

## Workflow

1. Select one of Simret's 48 assigned cases. All72 mode also shows24 read-only reference cases.
2. Read task, criterion, original labels, evidence excerpts, and source trajectory. The optional hide toggle conceals comparison annotations for an initial independent review.
3. Edit final verdict, overall reasoning, step labels, or evidence. Select a continuous quote in a raw field and use its add button, or add evidence manually. A new excerpt starts with pass; explicitly check its label.
4. Enter reviewer identity and rationale, then save the case. Leaving an unsaved case requires confirmation. Saved revisions persist in browser localStorage, not in the source JSON file.
5. Export both revised annotations and the review backup. The export dialog also displays selectable JSON if browser downloads are unavailable. Import uses the backup format.

The revised export retains all48 annotation entries and the original annotations structure. Unreviewed cases remain unchanged. Reviewed cases include source hashes, reviewer attribution, rationale, and history in `review_provenance`; `meta.annotator_id` is `Simret_revised`, not an attribution of the reviewer's edits to Simret. Do not treat revisions made after viewing other annotations as independent pre-adjudication labels for inter-annotator agreement.

Yukun's originally assigned48 are represented by the corresponding final golden records, based on the user's confirmation that they are identical. Golden is not displayed as independent Yukun annotation outside that assignment. Original files are never changed.

## Rebuild

Run `python3 -B technical_evaluation/annotation/verdict_review/build_simret_audit.py` from the EvalAgent repository after building the base verdict-review dataset. Source fingerprints are checked before embedding raw annotations.

`?test=1` isolates UI tests from real revisions and marks exports as test data. Dataset-specific storage prevents accidental mixing after changing input files. Export backups before rebuilding with different inputs.

Verified in browser: case rendering, adding/editing/deleting evidence, literal-quote validation on a valid excerpt, required review metadata, save/reload persistence, revised48 export payload, empty-evidence filter, no-results filter, separate test storage, and no console errors during those checks. Native file download and backup import have not been end-to-end tested.
