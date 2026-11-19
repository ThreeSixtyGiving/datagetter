import json
import pytest
import http.server
import socketserver
import os
import threading
import time
import shutil
from types import SimpleNamespace
from unittest.mock import Mock

import requests

import getter.get as getter_module
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


@pytest.mark.parametrize(
    ("content_type", "body"),
    [
        (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            b"Not a spreadsheet",
        ),
        ("application/json", b'{"error": "Not found"}'),
    ],
)
def test_failed_http_download_does_not_enter_processing(
    monkeypatch, tmp_path, content_type, body
):
    data_dir = tmp_path / "data"
    getter_module.mkdirs(data_dir)
    args = SimpleNamespace(data_dir=data_dir, publisher_prefixes=None)
    url = "https://publisher.example/grants"
    dataset = {
        "identifier": "missing",
        "distribution": [{"downloadURL": url}],
        "license": getter_module.acceptable_licenses[0],
    }
    response = requests.Response()
    response.url = url
    response.status_code = 404
    response.headers["Content-Type"] = content_type
    response._content = body
    cache_hash = Mock(return_value="test-hash")
    cache_lookup = Mock(return_value=False)
    cache_update = Mock()
    convert = Mock()
    validate = Mock()
    monkeypatch.setattr(getter_module.session, "get", Mock(return_value=response))
    monkeypatch.setattr(getter_module, "Schema360", Mock())
    monkeypatch.setattr(cache, "hash_file", cache_hash)
    monkeypatch.setattr(cache, "get_file", cache_lookup)
    monkeypatch.setattr(cache, "update_cache", cache_update)
    monkeypatch.setattr(getter_module, "convert_spreadsheet_file", convert)
    monkeypatch.setattr(getter_module, "validate", validate)

    result = getter_module.fetch_and_convert(args, dataset, "", "")

    metadata = result["datagetter_metadata"]
    assert not metadata["downloads"]
    assert "404" in metadata["error"]
    assert metadata.get("json") is None
    assert not list((data_dir / "original").iterdir())
    assert not list((data_dir / "json_all").iterdir())
    cache_hash.assert_not_called()
    cache_lookup.assert_not_called()
    cache_update.assert_not_called()
    convert.assert_not_called()
    validate.assert_not_called()
