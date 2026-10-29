"""SlayQL v1.8 answer-plan and tournament research-suite entry point."""

from __future__ import annotations

import os

os.environ["SLAYQL_RESEARCH_SUITE_VERSION"] = "1.8"

import research_suite  # noqa: E402


if __name__ == "__main__":
    research_suite.main()
