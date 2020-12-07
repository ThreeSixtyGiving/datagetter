#!/usr/bin/env python3
from getter.get import get
import argparse


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('--no-download', dest='download', action='store_false',
            help="Don't download any files only convert existing data")

    parser.add_argument('--local-registry', dest='local_registry', action='store_true',
            help="Use a local registry file rather than data.threesixtygiving.org",
            default=False)

    parser.add_argument('--no-convert', dest='convert', action='store_false')
    parser.add_argument('--no-convert-big-files', dest='convert_big_files', action='store_false')
    parser.add_argument('--no-validate', dest='validate', action='store_false')
    parser.add_argument('--data-dir', dest='data_dir', action='store',
                        default="data")
    parser.add_argument('--threads', dest='threads', action='store', type=int,
                        default=4)
    parser.add_argument('--socks5', dest='socks5_proxy', action='store',
                        help="Use a socks5 proxy to fetch publisher data. Example --socks5=socks5://host:port",
                        default=None)

    args = parser.parse_args()

    get(args)


if __name__ == "__main__":
    main()
