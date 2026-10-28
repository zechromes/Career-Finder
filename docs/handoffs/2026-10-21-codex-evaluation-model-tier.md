# Comparable-tier evaluation defaults

- Objective: user clarified that Gemini/GPT should use models in a stronger capability tier alongside Claude Sonnet 5.5, rather than align scoring settings.
- Tool/model: Codex / GPT-6 session; no Git branch available.
- Changed: backend evaluation defaults, environment example, evaluation-model guide, frontend mocked model options and backend model-configuration tests.
- Defaults: Claude remains claude-sonnet-5-5; GPT changes from gpt-4o-mini to gpt-6.1-sol; Gemini changes from gemini-3.6-flash to gemini-4-argon. Official provider pages verified model IDs and structured-output support. GPT now explicitly uses JSON-schema output, avoiding tool-calling compatibility ambiguity. No prompt, scoring, extraction-model, embedding-model or provider concurrency changes.
- Compatibility: environment overrides remain supported. No local evaluation overrides were configured when inspected; key contents were not displayed or changed. Model identity isolates cached assessments; saved historical results are not automatically reevaluated. New model account access and real-world latency remain unverified.
- Validation: standard check passed: 215 backend, 60 frontend, 1 legacy test, generated contracts and build. One mocked browser comparison/mobile workflow passed. No live model requests. No human-labeled dataset exists; comparable tier is a selection judgment, not measured equality or improved match accuracy. Costs may increase from smaller prior defaults.
- Skills: OpenAI Docs plus backend/test/evaluation responsibilities; evaluation skill retains documented role mismatch, so shared evaluation rules used. Official references recorded in evaluation guide.
- Remaining work: restart backend to apply; no implementation work remains. Live quality/cost comparison needs separately authorized evaluation data and calls.
