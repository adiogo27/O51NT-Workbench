# Structured extractor

This Claude Platform agent quickstart's setup as declarative files for the
`ant` CLI:

- `agents/structured-extractor.md`: the agent. Its YAML frontmatter is the body of `POST /v1/agents`; the Markdown under it is the system prompt.

Install the `ant` CLI (https://platform.claude.com/docs/en/cli-sdks-libraries/cli/quickstart), preview the plan, then apply it (https://platform.claude.com/docs/en/cli-sdks-libraries/cli/scripting#version-controlling-api-resources):

```sh
cd structured-extractor
ant apply --dry-run .
ant apply .
```

`claude-lock.json` already holds the IDs of what the quickstart created, so the first apply adopts those resources (one update each, stamping them as managed by `ant`) and later runs keep them in sync with these files. To create fresh copies instead — in another organization or workspace, say — delete `claude-lock.json` first.

Keep `claude-lock.json` next to these files, and the file names as they are (the IDs are keyed by path). Vault credentials aren't included; a credential typed into the agent config itself (an MCP server's `authorization_token`) is, so move it to a vault before committing these files.
