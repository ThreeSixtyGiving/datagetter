#!/usr/bin/env python3
from getter.get import get
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-download', dest='download', action='store_false')
    parser.add_argument('--no-convert', dest='convert', action='store_false')
    parser.add_argument('--no-convert-big-files', dest='convert_big_files', action='store_false')
    parser.add_argument('--no-validate', dest='validate', action='store_false')
    parser.add_argument('--data-dir', dest='data_dir', action='store',
                        default="data")

    args = parser.parse_args()

    print(args)

    get(args)


if __name__ == "__main__":
    main()
