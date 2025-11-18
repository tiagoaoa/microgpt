# gptcli

Small one-shot CLI that talks to OpenAI's Chat Completions API and optionally keeps a running conversation state.

## Installation

1. Ensure Python 3.13 (or similar) is available.
2. Install the OpenAI SDK (already done if you followed the earlier instructions):
   ```bash
   python3 -m pip install --user --break-system-packages openai
   ```
3. Make sure `~/bin` is on your `PATH` (most shells do this by default) so you can run `gptcli` from anywhere.
4. Set your API key before invoking the CLI:
   ```bash
   export OPENAI_API_KEY=sk-...
   ```

## Usage

Typical invocation:

```bash
gptcli -s mysession -p "Summarize this article"
```

- `--new`: perform a one-off call that skips saving any state.
- `-p/--prompt`: pass the prompt inline; if omitted the CLI reads from stdin.
- `-sin/--stdin`: append piped stdin to the `-p` prompt (e.g., prepend instructions, append source text).
- `-s/--state`: provide a friendly name for the conversation. Files live under `~/.cache/gptcli/NAME`.
- `--system`, `--model`, `--temperature`: optional overrides for the conversation configuration.

Combine inline instructions with piped content like so:

```bash
cat report.md | gptcli -s audit -p "Summarize the stdin content above" --stdin
```

## Conversation State Behavior

- All state files are now stored inside `~/.cache/gptcli/`.
- After each successful non-`--new` run, the CLI records the state name in `~/.cache/gptcli/.last_state`.
- If you invoke `gptcli` without `--new` and omit `-s`, it automatically reuses the most recently used state.
- To start a brand new conversation, pass a new name via `-s` or run with `--new` to keep it ephemeral.

This workflow lets you do:

```bash
gptcli -s research -p "Outline my idea"   # creates ~/.cache/gptcli/research
gptcli -p "Continue the outline"          # reuses the last state automatically
```
