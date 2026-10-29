"""SlayQL v1.3 entry point.

The implementation is shared with the v1.2 research harness; the environment
flag selects the version-gated selector and interaction behavior while keeping
separate manifests and run IDs.
"""

from __future__ import annotations

import os

os.environ["SLAYQL_RESEARCH_SUITE_VERSION"] = "1.3"

import research_suite  # noqa: E402


if __name__ == "__main__":
    research_suite.main()
