
import argparse
from pathlib import Path

def run(trade_date: str):
    """
    TODO:
    1. trade day check
    2. collect normalized market/disclosure/policy/industry data
    3. build candidate themes
    4. invoke Codex/LLM with prompts/SYSTEM_PROMPT.md + DAILY_TASK_PROMPT.md
    5. validate JSON
    6. compare with previous trade day
    7. save markdown/json/sqlite
    """
    print(f"[A股复盘] target_date={trade_date}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="auto")
    args = parser.parse_args()
    run(args.date)
