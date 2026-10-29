"""SlayQL v1.6 semantic-contract routed research-suite entry point."""

from __future__ import annotations

import os

os.environ["SLAYQL_RESEARCH_SUITE_VERSION"] = "1.6"

import research_suite  # noqa: E402


if __name__ == "__main__":
    research_suite.main()
