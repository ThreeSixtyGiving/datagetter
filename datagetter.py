#!/usr/bin/env python3
from getter.get import get
import argparse


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--local-registry",
        dest="local_registry",
        action="store",
        help="Use a local registry file rather than registry.threesixtygiving.org",
        default=False,
    )

    parser.add_argument("--data-dir", dest="data_dir", action="store", default="data")
    parser.add_argument(
        "--threads",
        dest="threads",
        action="store",
        type=int,
        default=4,
        help="Defaults to 4 threads",
    )

    parser.add_argument(
        "--limit-downloads",
        dest="limit_downloads",
        action="store",
        type=int,
        help="Limit the number of file downloads",
        default=None,
    )

    parser.add_argument(
        "--schema-branch",
        dest="schema_branch",
        action="store",
        type=str,
        help="Specify a git branch of the 360Giving schema",
        default="main",
    )

    parser.add_argument(
        "--publishers",
        nargs="+",
        dest="publisher_prefixes",
        action="store",
        type=str,
        help="Only download for selected publishers",
    )

    args = parser.parse_args()

    get(args)


if __name__ == "__main__":
    main()
