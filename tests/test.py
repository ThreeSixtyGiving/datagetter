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

import getter.get as getter
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
    "original_path, final_path, headers, expected",
    [
        ("/download", "/grants.XLSX?X-Amz-Signature=example", {"Content-Type": "binary/octet-stream"}, "xlsx"),
        (
            "/grants.csv",
            "/grants.xlsx",
            {"Content-Type": "application/vnd.oasis.opendocument.spreadsheet; charset=UTF-8"},
            "ods",
        ),
        ("/grants.csv", "/grants.xlsx", {"Content-Disposition": 'attachment; filename="grants.ODS"'}, "ods"),
        ("/grants.CSV?download=1#source", "/grants.xlsx", {}, "csv"),
        ("/download", "/grants.xlsx", {"Content-Disposition": 'attachment; filename="export.bin"'}, "xlsx"),
        ("/download?name=grants.csv", "/download?name=grants.xlsx", {}, None),
    ],
)
def test_fetch_and_convert_guesses_file_type(tmp_path, monkeypatch, original_path, final_path, headers, expected):
    source_url = f"https://registry.example{original_path}"
    data_dir = tmp_path / "output"
    getter.mkdirs(data_dir)
    args = SimpleNamespace(data_dir=data_dir, publisher_prefixes=None)
    dataset = {
        "identifier": "test-grants",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "distribution": [{"downloadURL": source_url}],
    }
    response = requests.Response()
    response.status_code = 200
    response.url = f"https://publisher.example{final_path}"
    response.headers.update(headers)
    response._content = b"mock spreadsheet"
    download = Mock(return_value=response)
    monkeypatch.setattr(getter.session, "get", download)
    monkeypatch.setattr(getter, "Schema360", Mock())
    monkeypatch.setattr(getter.cache, "get_file", lambda *_: None)
    monkeypatch.setattr(getter.cache, "update_cache", Mock())
    monkeypatch.setattr(getter, "validate", Mock())
    for result_list in ("data_valid", "data_acceptable_license", "data_acceptable_license_valid"):
        monkeypatch.setattr(getter, result_list, [])

    def write_json(_directory, _schema, _source, destination, _file_type):
        with open(destination, "w") as output:
            json.dump({"grants": []}, output)

    convert = Mock(side_effect=write_json)
    monkeypatch.setattr(getter, "convert_spreadsheet_file", convert)
    result = getter.fetch_and_convert(args, dataset, None, None)

    download.assert_called_once()
    assert download.call_args.args == (source_url,)
    assert result["datagetter_metadata"]["downloads"] is True
    assert result["datagetter_metadata"].get("file_type") == expected
    if expected:
        convert.assert_called_once()
        assert convert.call_args.args[-1] == expected
        assert (data_dir / "original" / f"test-grants.{expected}").read_bytes() == response.content
    else:
        convert.assert_not_called()
        assert not list((data_dir / "original").iterdir())
