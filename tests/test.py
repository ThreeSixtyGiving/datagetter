import json
import pytest
import http.server
import socketserver
import os
import threading
import time
import shutil
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import requests
from openpyxl import Workbook

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
    ("failure", "error"),
    [
        ("unreadable", "Could not open spreadsheet"),
        ("invalid_data", "Could not unflatten spreadsheet data"),
        ("unexpected_error", "Could not unflatten file"),
    ],
)
def test_reports_distinct_spreadsheet_failures(
    monkeypatch, tmp_path, capsys, failure, error
):
    data_dir = tmp_path / "data"
    getter_module.mkdirs(data_dir)
    args = SimpleNamespace(data_dir=data_dir, publisher_prefixes=None)
    url = "https://publisher.example/grants.xlsx"
    dataset = {
        "identifier": "example",
        "distribution": [{"downloadURL": url}],
        "license": getter_module.acceptable_licenses[0],
    }

    response = requests.Response()
    response.url = url
    response.status_code = 200
    response.headers["Content-Type"] = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    if failure == "invalid_data":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "grants"
        sheet.append(["Identifier", "Amount Awarded:0"])
        sheet.append(["example", 1])
        contents = BytesIO()
        workbook.save(contents)
        workbook.close()
        response._content = contents.getvalue()
    else:
        response._content = b"Not an XLSX archive"

    schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "title": "Identifier"},
            "amountAwarded": {"type": "number", "title": "Amount Awarded"},
        },
    }
    monkeypatch.setattr(getter_module.session, "get", Mock(return_value=response))
    monkeypatch.setattr(
        getter_module,
        "Schema360",
        Mock(return_value=Mock(schema_file=schema, pkg_schema_file=None)),
    )
    monkeypatch.setattr(cache, "get_file", Mock(return_value=False))
    cache_update = Mock()
    validate = Mock()
    monkeypatch.setattr(cache, "update_cache", cache_update)
    monkeypatch.setattr(getter_module, "validate", validate)
    if failure == "unexpected_error":
        monkeypatch.setattr(
            getter_module,
            "convert_spreadsheet_file",
            Mock(side_effect=RuntimeError("conversion bug")),
        )

    result = getter_module.fetch_and_convert(args, dataset, None, None)

    metadata = result["datagetter_metadata"]
    assert metadata["error"] == error
    assert metadata["downloads"] is True
    assert metadata["valid"] is False
    assert metadata["json"] is None
    assert not (data_dir / "json_all" / "example.json").exists()
    output = capsys.readouterr()
    assert error in output.out
    assert "example.xlsx" in output.out
    assert "Traceback" in output.err
    validate.assert_not_called()
    cache_update.assert_not_called()
