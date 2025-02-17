#!/usr/bin/env python3
from getter.get import get
import argparse


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--no-download",
        dest="download",
        action="store_false",
        help="Don't download any files only convert existing data",
    )

    parser.add_argument(
        "--local-registry",
        dest="local_registry",
        action="store",
        help="Use a local registry file rather than registry.threesixtygiving.org",
        default=False,
    )

    parser.add_argument("--no-convert", dest="convert", action="store_false")
    parser.add_argument(
        "--no-convert-big-files", dest="convert_big_files", action="store_false"
    )
    parser.add_argument("--no-validate", dest="validate", action="store_false")
    parser.add_argument("--data-dir", dest="data_dir", action="store", default="data")
    parser.add_argument(
        "--threads", dest="threads", action="store", type=int, default=4
    )
    parser.add_argument(
        "--socks5",
        dest="socks5_proxy",
        action="store",
        help="Use a socks5 proxy to fetch publisher data. Example --socks5=socks5://host:port",
        default=None,
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
        default="master",
    )

    parser.add_argument(
        "--publishers",
        nargs="+",
        dest="publisher_prefixes",
        action="store",
        type=str,
        help="Only download for selected publishers",
    )

    parser.add_argument(
        "--file",
        dest="test_file",
        action="store",
        type=str,
        help="Test a particular file",
    )

    args = parser.parse_args()

    get(args)


if __name__ == "__main__":
    main()
