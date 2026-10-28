# Animated flowchart and technical workflow guide

- Objective: replace the chapter-only presentation with a connected animated flowchart and explain technical behavior accessibly in Markdown.
- Tool/model: Codex / GPT-6 session; no Git repository/branch available.
- Changed: docs/images/application-workflow-flowchart.html, docs/images/application-workflow-flowchart.gif, docs/application-workflow-technical-guide.md, README.md.
- Diagram: full graph stays visible; 11 highlighted stages, moving connector dots, three parallel provider branches, extraction/assessment failure route, targeted retry loop and Find more loop. HTML has playback, scrubbing, clickable/keyboard nodes and reduced-motion support. GIF is 1460×1240, 110 seconds.
- Guide: architecture, stage inputs/outputs, upload limits, hybrid retrieval/RRF, shared extraction v5, provider configuration, evidence formula and category guards, aggregation, retries/cancellation, storage/caches, HTTP route map, persistence and known limits. Code links support the explanations. No application contracts changed.
- Accuracy: inspected current backend routes, upload/confirmation, collection/index/retrieval, requirements, orchestration, providers, evidence/experience, persistence and frontend progress. Diagram describes per-posting logical ordering, not a global barrier. Cache hits may skip calls; scoring/persistence happen incrementally.
- Verification: Chromium rendered 88 source frames; node text fits; previous/next, Play/Pause, keyboard node selection and mobile contained scrolling passed with no page errors. Visually inspected provider-fork and Find more scenes; corrected connector/label overlaps. Guide source links, heading anchors and new README links resolve. GIF frame durations total 110 seconds. Application tests not run for documentation-only artifacts.
- Existing prior animation/image/detail artifacts were absent from docs/images; removed dangling workflow links from README rather than restoring deleted files. Unrelated documentation retained.
- Skill: project-manager documentation review applied; no agents spawned, no private data, no live provider requests, no new dependencies. Temporary renderer and source frames are under /tmp.
- Next: open HTML for controllable playback, share GIF, use technical guide for implementation details. Re-review after workflow changes.
