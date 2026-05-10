# RW Power BI MCP and Tooling Review

Date: 2026-05-09

## Readout

Power BI MCP can help this project, but it will not directly solve Zebra visual
styling. The bridge problem has three separate layers:

1. **Semantic model and DAX correctness** - good fit for Power BI Modeling MCP
   and Remote Power BI MCP.
2. **Fabric workspace and item management** - good fit for Fabric Core MCP or
   our existing Fabric REST wrappers.
3. **Report page rendering and visual styling** - still requires PBIR JSON,
   Power BI Desktop, screenshots, and captured renderer-valid visual shapes.

## Probe Results

Local environment:

- Node and npm are present.
- `npx -y @microsoft/powerbi-modeling-mcp@latest --help` works, so the official
  local Modeling MCP package is reachable.
- Starting the package resolves to
  `@microsoft/powerbi-modeling-mcp-darwin-arm64` version `0.5.0-beta.6`.
- Power BI Desktop is installed in the Parallels VM:
  `C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe`.

Tenant/API probe:

- Remote Power BI MCP endpoint:
  `https://api.fabric.microsoft.com/v1/mcp/powerbi`
  returned `403 FeatureNotAvailable`.
- A real MCP `initialize` POST was tested with both token audiences:
  `https://api.fabric.microsoft.com/.default` and
  `https://analysis.windows.net/powerbi/api/.default`. Both returned
  `403 FeatureNotAvailable`, so this is tenant feature availability, not a
  client handshake or token-audience mistake.
- That matches Microsoft docs: the Power BI admin must enable the tenant setting
  for the Power BI MCP endpoint before users can use it.
- Fabric Core MCP endpoint:
  `https://api.fabric.microsoft.com/v1/mcp/core`
  exists, but it needs a real MCP HTTP/OAuth handshake. A plain GET returns a
  method/protocol error, which is expected.

## Tool Fit

### Official Power BI Modeling MCP

Best for:

- TMDL / PBIP semantic model work
- tables, columns, measures, relationships
- bulk model operations
- DAX validation when connected to a supported Desktop/Fabric model

Not enough for:

- report page visual polish
- custom visual approval
- Zebra visual rendering

Important Microsoft caveat: Modeling MCP cannot modify report-page metadata.

### Remote Power BI MCP

Best for:

- asking questions against existing semantic models
- schema-aware DAX generation
- executing DAX through an authenticated user

Current blocker:

- SimCorp tenant currently returns `FeatureNotAvailable`; admin enablement is
  required.

Admin ask:

> Please enable the tenant setting "Users can use the Power BI Model Context
> Protocol server endpoint (preview)" for `apro@simcorp.com` or the Sales Ops
> Power BI security group.

### Fabric Core MCP

Best for:

- listing workspaces/items
- creating workspaces/items
- managing item permissions
- natural-language wrapper over Fabric item operations

Overlap with current repo:

- We already have direct Fabric REST wrappers for report/semantic-model
  `getDefinition`, `updateDefinition`, and item creation.
- Fabric Core MCP could make those operations easier to drive interactively, but
  it does not replace the custom report conversion logic.

### Repo-Local Power BI Operator MCP

This is the missing layer for Codex/Claude. It should wrap our proven scripts as
tools:

- `pbi_get_report_definition`
- `pbi_update_report_definition`
- `pbi_list_items`
- `pbi_validate_report_refs`
- `pbi_capture_visual`
- `pbi_native_layout_publish`
- `pbi_native_layout_verify`
- `pbi_open_report`
- `pbi_desktop_launch`
- `pbi_screenshot_gate`

This would turn the current script pile into a stable operator interface without
depending on tenant-preview MCP features.

## Recommended Path

1. **Keep using repo REST wrappers for report-layer work.**
   They are already tenant-proven and handle the PBIR-Legacy definitions we
   need.

2. **Add official Power BI Modeling MCP for semantic-model work.**
   Use it for measures, relationships, descriptions, best-practice checks, and
   DAX validation where it can connect.

3. **Request admin enablement for Remote Power BI MCP.**
   It is the cleanest analytics/chat-with-model path, but it is currently
   tenant-disabled.

4. **Build a local `pbi-operator` MCP wrapper around this repo.**
   That gives Codex/Claude stable tools for the exact workflows that matter:
   publish, verify, capture, diff, screenshot, and rollback.

5. **Use Desktop analytics for visual truth.**
   Power BI Desktop Performance Analyzer and screenshot capture should become
   the renderer gate for any advanced dashboard polish.

## Why This Matters

The Zebra issue showed that API success is not dashboard success. The bridge
needs tool separation:

- MCP/model tools tell us whether the data model and DAX are correct.
- Fabric item tools tell us whether definitions round-trip.
- Desktop/browser visual gates tell us whether the page actually looks good.

No single MCP server replaces all three.
