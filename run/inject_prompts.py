import re

mcp_instruction_gen = """**Step 2: Utilize MCP Analytical Tools**
If you encounter domain-specific terms, date format ambiguities, structural uncertainties, or complex topological graph paths, YOU MUST call the appropriate function tools provided to you:
- Use `lookup_business_term` for industry/domain-specific magic strings (e.g. 'breast cancer', 'purchase action').
- Use `profile_column_values` whenever encountering date or string-matching ambiguities.
- Use `get_shortest_join_path` if you are unsure how to connect two distant tables.
- Use `dry_run_query` to validate structurally uncertain SQL queries *before* writing your final answer.

**Step 3: Identify Relevant Tables and Columns**"""

mcp_instruction_rev = """**Utilize MCP Analytical Tools**
If you encounter domain-specific terms, date format ambiguities, structural uncertainties, or complex topological graph paths, YOU MUST call the appropriate function tools provided to you:
- Use `lookup_business_term` for industry/domain-specific magic strings (e.g. 'breast cancer', 'purchase action').
- Use `profile_column_values` whenever encountering date or string-matching ambiguities.
- Use `get_shortest_join_path` if you are unsure how to connect two distant tables.
- Use `dry_run_query` to validate structurally uncertain SQL queries *before* outputting your final revised SQL.

The SQL you generated:
{SQL}"""

with open("config.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update SQL_GENERATION
content = content.replace("**Step 2: Identify Relevant Tables and Columns**", mcp_instruction_gen)

# 2. Update REVISE_ERROR
content = content.replace("The SQL you generated:\n{SQL}", mcp_instruction_rev)

with open("config.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Successfully injected MCP prompts into config.py")
