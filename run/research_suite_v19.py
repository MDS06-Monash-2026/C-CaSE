"""SlayQL v1.9 adaptive-schema and projection-contract research suite."""

from __future__ import annotations

import os

os.environ["SLAYQL_RESEARCH_SUITE_VERSION"] = "1.9"

import research_suite  # noqa: E402


if __name__ == "__main__":
    research_suite.main()
