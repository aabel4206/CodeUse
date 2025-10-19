"""Demonstration script for the Role C bridge."""

from __future__ import annotations

import json
import pathlib
import sys

from dotenv import load_dotenv

from tool.pipeline.bridge import process_executor_result


def main() -> int:
    load_dotenv()

    if len(sys.argv) < 2:
        print("Usage: python examples/bridge_demo.py <executor_json_path> [user_prompt]")
        return 2

    input_path = pathlib.Path(sys.argv[1])
    if not input_path.exists():
        print(f"Input file not found: {input_path}")
        return 1

    raw_executor = json.loads(input_path.read_text(encoding="utf-8"))
    user_prompt = sys.argv[2] if len(sys.argv) > 2 else None

    bridge_out = process_executor_result(raw_executor, user_prompt=user_prompt)

    ui_path = pathlib.Path(bridge_out.result_json_path).with_name("ui.json")
    ui_path.write_text(json.dumps(bridge_out.ui_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"RUN: {bridge_out.run_id}")
    print(f"RESULT JSON: {bridge_out.result_json_path}")
    print(f"UI JSON: {ui_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

