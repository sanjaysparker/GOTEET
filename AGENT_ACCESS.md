# GOTEET live agent access

The installed desktop owns the backend. Its bundled executable supports `--cli` and `--mcp`, so installed agent access does not need a separate Python environment. The local API requires an owner bearer token from the private runtime file; clients discover it automatically. No keys appear in CLI help, MCP config or source files.

## CLI

`/Users/sanju/.local/bin/goteet` points to the project CLI. Examples:

```sh
goteet status
goteet media --value screenshot
goteet navigate --value Media
goteet preview --value '/absolute/indexed/image.png'
goteet ui
goteet models
```

`goteet ui` returns UI acknowledgement and current route/preview. Commands expire after 60 seconds. `draft` fills the assistant without sending; UI controls never evaluate arbitrary JavaScript or send chat messages.

## MCP

The `goteet` stdio server is registered with the local Codex CLI. Claude Code uses the project `.mcp.json` and currently reports its normal MCP approval as pending. New sessions may require their normal MCP trust/reload step. Existing unrelated MCP servers were preserved.

19 tools cover status, tasks, projects, concepts, channels, reports, media search, UI control model status, file browsing, system health, agent inventory and reviewed plans. `goteet_control_ui` supports `navigate`, `search`, `open_media`, `close_media`, and `draft_assistant`. Shared messages still require an explicit human request.

## CDP

Quit an existing instance before changing mode, then:

```sh
goteet launch --cdp 9223
```

This enables Electron's Chrome DevTools Protocol on loopback. Discovery is `http://127.0.0.1:9223/json/list`; a CDP client can inspect the actual desktop renderer. Connections shows whether CDP is enabled. It is disabled on normal launch; no main-process Node inspector is enabled. CDP grants interface access to local clients and must not be forwarded to a public network.

## Model setup

Models is the dedicated account/provider page. Codex and Claude log in using their official installed CLIs. API providers use OS keyring storage. OpenAI, Anthropic, NVIDIA NIM, OpenRouter and Gemini have fixed HTTPS endpoints, configured model IDs and verification. The assistant supports read-only questions or schema-validated proposals that require Apply.

Local downloads go through the running Ollama daemon, including public Hugging Face GGUF IDs of the form `hf.co/owner/repository:quantization`. Not every Hugging Face model format is an Ollama model. The original model license and machine requirements still apply. Download progress and failure states appear in Models.

## Updates

About GOTEET contains update-source setup and Check for updates. A public GitHub repository with published releases is required. This unsigned MVP opens the release installer page when a newer stable version exists; signed automatic installation is not configured. No release repository was invented or published.
