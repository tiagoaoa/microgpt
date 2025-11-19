#!/usr/bin/env python3
"""
chatgptcli.py — tiny, no‑menu CLI for ChatGPT

Examples
--------
# 1) One‑off, ephemeral chat (not saved)
$ ./chatgptcli.py --new -p "Answer this question..."

# 2) Continue a saved conversation stored in chat.gpt
$ ./chatgptcli.py -p "Answer question 2 blablabal" -s chat.gpt

# 3) Read the prompt from stdin when -p is omitted
$ echo "Analyze this report: $(./program)" | ./chatgptcli.py -s chat.gpt

Notes
-----
- Requires OPENAI_API_KEY to be set in the environment.
- Uses the official OpenAI Python SDK v1 (`pip install openai`).
- No menus, no REPL; runs once and prints the assistant reply to stdout.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    from openai import OpenAI  # OpenAI Python SDK v1+
except Exception as e:
    sys.stderr.write("[chatgptcli] Missing dependency: pip install openai\n")
    raise


STATE_DIR = Path.home() / ".cache" / "gptcli"
LAST_STATE_FILE = STATE_DIR / ".last_state"


def die(msg: str, code: int = 2) -> None:
    sys.stderr.write(f"[chatgptcli] {msg}\n")
    sys.exit(code)


def read_prompt_from_stdin() -> str:
    if sys.stdin is None or sys.stdin.closed:
        return ""
    # If stdin is a TTY and no -p provided, there's no input to read
    if sys.stdin.isatty():
        return ""
    data = sys.stdin.read()
    return data.strip()


def ensure_api_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        die("OPENAI_API_KEY is not set in the environment.")


def ensure_state_dir() -> Path:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        die(f"Unable to create state directory '{STATE_DIR}': {e}")
    return STATE_DIR


def list_state_files() -> List[Path]:
    state_dir = ensure_state_dir()
    return [
        p
        for p in state_dir.iterdir()
        if p.is_file() and p != LAST_STATE_FILE
    ]


def get_last_state_name() -> Optional[str]:
    try:
        last = LAST_STATE_FILE.read_text(encoding="utf-8").strip()
        if last:
            return last
    except FileNotFoundError:
        pass
    except OSError:
        pass

    candidates = list_state_files()
    if not candidates:
        return None
    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    return newest.name


def update_last_state(path: Path) -> None:
    try:
        LAST_STATE_FILE.write_text(path.name, encoding="utf-8")
    except Exception as e:
        sys.stderr.write(f"[chatgptcli] Warning: could not update last state marker: {e}\n")


def resolve_state_path(state_arg: Optional[Path]) -> Path:
    state_dir = ensure_state_dir()
    if state_arg:
        name = Path(state_arg).name
        if not name:
            die("State name cannot be empty.")
        return state_dir / name

    last = get_last_state_name()
    if last:
        return state_dir / last
    die("No state specified and no previous states exist. Use -s to name a new state or --new for ephemeral.")


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"system": None, "model": None, "messages": []}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        die(f"State file '{path}' is not valid JSON.")
    except Exception as e:
        die(f"Could not read state file '{path}': {e}")


def save_state(path: Path, state: Dict[str, Any]) -> None:
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        tmp.replace(path)
    except Exception as e:
        die(f"Could not write state file '{path}': {e}")


def build_messages(state: Dict[str, Any]) -> List[Dict[str, str]]:
    msgs: List[Dict[str, str]] = []
    if state.get("system"):
        msgs.append({"role": "system", "content": state["system"]})
    msgs.extend(state.get("messages", []))
    return msgs


def call_openai(model: str, messages: List[Dict[str, str]], temperature: float) -> str:
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    try:
        return resp.choices[0].message.content or ""
    except Exception:
        # Fall back to printing the whole response if structure differs
        return json.dumps(resp.model_dump(), indent=2)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="gptcli",
        description="One‑shot ChatGPT CLI with optional saved conversation state.",
        add_help=True,
    )

    subparsers = parser.add_subparsers(dest="command")

    ls_parser = subparsers.add_parser("ls", help="List available saved states and exit.")
    ls_parser.set_defaults(command="ls")

    rm_parser = subparsers.add_parser("rm", help="Delete a saved state and exit.")
    rm_parser.add_argument("name", help="Name of the state to delete.")
    rm_parser.set_defaults(command="rm")

    ren_parser = subparsers.add_parser("rename", help="Rename a saved state and exit.")
    ren_parser.add_argument("old", help="Existing state name.")
    ren_parser.add_argument("new", help="New name for the state.")
    ren_parser.set_defaults(command="rename")

    parser.add_argument("-p", "--prompt", help="Prompt text; if omitted, read from stdin.")
    parser.add_argument("-sin", "--stdin", action="store_true", help="Force stdin to be read too, even with -p.")
    parser.add_argument(
        "-s",
        "--state",
        type=Path,
        help="Name of the conversation state (stored under ~/.cache/gptcli/).",
    )
    parser.add_argument("--new", action="store_true", help="Run one‑off chat (do not use or save state).")
    parser.add_argument("--system", help="System prompt to use when starting a new state.")
    parser.add_argument("--model", default="gpt-4o-mini", help="Model ID (default: gpt-4o-mini).")
    parser.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature (default: 0.2).")

    args = parser.parse_args(argv)

    if args.command == "ls":
        states = list_state_files()
        if not states:
            print("No saved states.")
            return 0
        for state in sorted(states, key=lambda p: p.name.lower()):
            print(state.name)
        return 0

    if args.command == "rm":
        target = ensure_state_dir() / Path(args.name).name
        if not target.exists():
            die(f"State '{target.name}' does not exist.")
        try:
            target.unlink()
        except Exception as e:
            die(f"Unable to delete state '{target.name}': {e}")
        try:
            if LAST_STATE_FILE.exists():
                last = LAST_STATE_FILE.read_text(encoding="utf-8").strip()
                if last == target.name:
                    LAST_STATE_FILE.unlink()
        except OSError:
            pass
        print(f"Deleted state '{target.name}'.")
        return 0

    if args.command == "rename":
        src = ensure_state_dir() / Path(args.old).name
        dst = ensure_state_dir() / Path(args.new).name
        if not src.exists():
            die(f"State '{src.name}' does not exist.")
        if dst.exists():
            die(f"State '{dst.name}' already exists.")
        try:
            src.rename(dst)
        except Exception as e:
            die(f"Unable to rename state '{src.name}': {e}")
        try:
            if LAST_STATE_FILE.exists():
                last = LAST_STATE_FILE.read_text(encoding="utf-8").strip()
                if last == src.name:
                    LAST_STATE_FILE.write_text(dst.name, encoding="utf-8")
        except OSError:
            pass
        print(f"Renamed '{src.name}' -> '{dst.name}'.")
        return 0

    ensure_api_key()

    # Source the prompt from -p or stdin
    prompt = read_prompt_from_stdin()
    if args.prompt:
        prompt = args.prompt + " " + (args.stdin and prompt or "")
    #prompt = args.prompt if args.prompt is not None else read_prompt_from_stdin()
    if not prompt:
        die("No prompt provided. Use -p or pipe input via stdin.")

    # Ephemeral path: ignore any provided -s
    if args.new:
        state = {"system": args.system, "model": args.model, "messages": []}
        msgs = build_messages(state)
        msgs.append({"role": "user", "content": prompt})
        reply = call_openai(args.model, msgs, args.temperature)
        print(reply)
        return 0

    # Resolve persistent conversation path, defaulting to most recent state
    state_path = resolve_state_path(args.state)

    state = load_state(state_path)

    # Initialize model/system if absent
    if state.get("model") is None:
        state["model"] = args.model
    if state.get("system") is None and args.system:
        state["system"] = args.system

    msgs = build_messages(state)
    msgs.append({"role": "user", "content": prompt})

    reply = call_openai(state["model"] or args.model, msgs, args.temperature)

    # Save updated conversation
    state.setdefault("messages", [])
    state["messages"].append({"role": "user", "content": prompt})
    state["messages"].append({"role": "assistant", "content": reply})

    save_state(state_path, state)
    update_last_state(state_path)

    # Print only the assistant's reply
    print(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
