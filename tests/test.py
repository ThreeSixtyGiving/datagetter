import json
import pytest
import http.server
import socketserver
import os
import threading
import time
from pathlib import Path
import sys
import shutil

sys.path.append(str(Path(__file__).resolve().parent.parent))

from getter.get import get
import getter.cache as cache

TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TEST_SERVER_PORT = 8888  # this is what the registry.json urls are expecting


class ReusableTCPServer(socketserver.TCPServer):
    """
    Sets allow_reuse_address to true from default of false. This is so that if
    the tests are rapidly run in succession we don't need to wait for the OS to
    fully close any open sockets (and thus resulting in an
    "Address already in use" error.
    """

    allow_reuse_address = True


def run_simple_server_daemon(port=TEST_SERVER_PORT):
    """
    Runs a simple HTTP server to simiulate a publisher.
    """
    os.chdir(os.path.join(TEST_DATA_DIR, "input"))

    def run_server():
        Handler = http.server.SimpleHTTPRequestHandler
        with ReusableTCPServer(("", port), Handler) as httpd:
            print("Webserver started")
            httpd.serve_forever()

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(0.1)

    return server_thread


@pytest.fixture(scope="session")
def test_server():
    server_thread = run_simple_server_daemon()
    yield f"http://127.0.0.1:{TEST_SERVER_PORT}"
    server_thread.join(1)


class DatagetterArgs(object):
    limit_downloads = None
    publisher_prefixes = None

    local_registry = os.path.join(TEST_DATA_DIR, "input", "registry.json")
    download = True
    schema_branch = "main"
    threads = 1
    data_dir = os.path.join(TEST_DATA_DIR, "fetched_output")


def test_expected_output(test_server):
    getter_args = DatagetterArgs()
    # remove any existing data
    try:
        shutil.rmtree(getter_args.data_dir)
    except FileNotFoundError:
        pass

    cache.delete_cache()

    # Run the datagetter
    get(getter_args)

    # produces
    expected_data_dir = os.path.join(TEST_DATA_DIR, "expected_output")
    fetched_output_dir = os.path.join(TEST_DATA_DIR, "fetched_output")

    fetched_data_all = json.load(
        open(os.path.join(fetched_output_dir, "data_all.json"))
    )
    expected_data_all = json.load(
        open(os.path.join(expected_data_dir, "data_all.json"))
    )

    def remove_known_differences(item):
        """
        Removes timestamp and full path which will be different
        depending on when/where this test is being run
        """
        del item["datagetter_metadata"]["datetime_downloaded"]
        if json_path := item["datagetter_metadata"].get("json"):
            item["datagetter_metadata"]["json"] = os.path.basename(json_path)

        return item

    # Remove known differences
    expected_data_all = [remove_known_differences(item) for item in expected_data_all]
    fetched_data_all = [remove_known_differences(item) for item in fetched_data_all]

    # Check data_all's match
    assert fetched_data_all == expected_data_all

    # Compare other files produced with the expected files
    for file in ["aninvalidfile.json", "conversionerrorsfile.json", "validfile.json"]:
        expected = json.load(open(os.path.join(expected_data_dir, "json_all", file)))
        fetched = json.load(open(os.path.join(fetched_output_dir, "json_all", file)))
        assert fetched == expected
