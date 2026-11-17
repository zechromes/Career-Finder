"""Career Tracker tests package."""

import os

# Never send the live model availability check from tests, even when a single
# test module runs outside scripts/check.sh with real keys in .env.
os.environ.setdefault("CAREER_EVALUATION_PREFLIGHT", "false")
# The default builder (hyde) writes job ads with a live model call; tests that want it mock
# the call and name the builder. Assigned, not defaulted, so a shell export cannot leak in.
os.environ["QUERY_BUILDER"] = "evidence"
