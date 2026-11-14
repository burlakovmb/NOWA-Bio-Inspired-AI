#!/usr/bin/env python3
"""Manual diagnostic for the newest agent save in saves/.

This is not part of the pytest suite. Running it as a script inspects the
latest save. Importing the module (as pytest does at collection) does nothing.
"""

import os
import sys
from pathlib import Path


def main() -> int:
    saves_dir = Path("saves")
    if not saves_dir.exists():
        print("No saves directory!")
        return 1

    files = sorted(
        list(saves_dir.glob("*.nowa")) + list(saves_dir.glob("*.pkl")),
        key=os.path.getmtime,
        reverse=True,
    )
    if not files:
        print("No save files!")
        return 1

    latest = files[0]
    print(f"Checking: {latest}")
    print(f"Size: {latest.stat().st_size} bytes")
    print()

    src = Path(__file__).resolve().parents[1] / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from storage import read_agent_state

    data = read_agent_state(latest)

    print("Keys in saved data:")
    for key in data.keys():
        print(f"  • {key}")

    print()
    print("sleep_manager content:")
    if "sleep_manager" in data:
        sm = data["sleep_manager"]
        print(f"  Type: {type(sm)}")
        print(f"  Keys: {list(sm.keys())}")

        for key, val in sm.items():
            print(
                f"  • {key}: {type(val)} = "
                f"{val if not isinstance(val, dict) else f'dict with {len(val)} keys'}"
            )

            if key == "chain_memory" and isinstance(val, dict):
                print(f"      chains key: {'chains' in val}")
                if "chains" in val:
                    print(f"      number of chains: {len(val['chains'])}")
                    if val["chains"]:
                        print(f"      first chain key: {list(val['chains'].keys())[0]}")
    else:
        print("  'sleep_manager' not in saved data!")

    print()
    print("[IMPORTANT] Check if your saved file was created BEFORE the chain save/load was fixed!")
    print("If so, you need to manually test with a NEW save that has chains.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
