"""Command line: turn one clip into skeleton JSON. Owner: Dev.

Usage (from services/):  python -m pipeline.run ../data/raw/aryan_fh_good_01.mov
"""

import json
import sys

from pipeline.pose import extract_pose


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m pipeline.run <clip>")
        sys.exit(1)
    swing = extract_pose(sys.argv[1])
    print(json.dumps(swing)[:500])


if __name__ == "__main__":
    main()
