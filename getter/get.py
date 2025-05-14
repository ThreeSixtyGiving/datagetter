import itertools
import json
import os
import shutil
import tempfile
import time
import traceback
from multiprocessing import Pool
import requests
from urllib3.util import Retry
from requests.adapters import HTTPAdapter
from decimal import Decimal
import email.headerregistry  # (content-disposition header parser)
import strict_rfc3339

from lib360dataquality.cove.schema import Schema360
from lib360dataquality.cove.settings import COVE_CONFIG
from lib360dataquality.cove.threesixtygiving import common_checks_360
from libcove.lib.converters import convert_spreadsheet
from libcove.config import LibCoveConfig

import getter.cache as cache


# These two lines enable debugging at httplib level (requests->urllib3->http.client)
# You will see the REQUEST, including HEADERS and DATA, and RESPONSE with HEADERS but without DATA.
# The only thing missing will be the response.body which is not logged.
HTTP_DEBUG = False

if HTTP_DEBUG:
    import http.client as http_client
    import logging

    http_client.HTTPConnection.debuglevel = 1

    # You must initialize logging, otherwise you'll not see debug output.
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True


acceptable_licenses = [
    "http://www.opendefinition.org/licenses/odc-pddl",
    "https://creativecommons.org/publicdomain/zero/1.0/",
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/2/",
    "http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    "https://creativecommons.org/licenses/by/4.0/",
    "https://creativecommons.org/licenses/by-sa/3.0/",
    "https://creativecommons.org/licenses/by-sa/4.0/",
]

unacceptable_licenses = [
    "",
    # Not relicenseable as CC-BY
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/1/",
    "https://creativecommons.org/licenses/by-nc/4.0/",
    "https://creativecommons.org/licenses/by-nc-sa/4.0/",
]

CONTENT_TYPE_MAP = {
    "application/json": "json",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/csv": "csv",
    "application/vnd.oasis.opendocument.spreadsheet": "ods",
}


data_valid = []
data_acceptable_license = []
data_acceptable_license_valid = []

session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=0.1,
    status_forcelist=[502, 503, 504],
    allowed_methods={"POST"},
)

session.mount("https://", HTTPAdapter(max_retries=retries))
session.mount("http://", HTTPAdapter(max_retries=retries))


def mkdirs(data_dir, exist_ok=False):
    try:
        os.makedirs(data_dir, exist_ok=exist_ok)
        for dir_name in [
            "original",
            "json_all",
            "json_valid",
            "json_acceptable_license",
            "json_acceptable_license_valid",
        ]:
            os.makedirs("%s/%s" % (data_dir, dir_name), exist_ok=exist_ok)
    except FileExistsError:
        q = input(f"Remove existing directory? {data_dir} y/n: ")
        if q.lower() == "y":
            shutil.rmtree(data_dir)
            mkdirs(data_dir, exist_ok=False)
        else:
            exit


class ValidationError(Exception):
    def __init__(self, errors_count, errors):
        self.errors_count = errors_count
        self.errors = errors
        message = f"Dataset has {errors_count} validation errors"
        super().__init__(message)


def validate(working_dir, schema_360, data):
    context = {"file_type": "json"}
    common_checks_360(context, working_dir, data, schema_360, test_classes=[])
    validation_errors_count = context["validation_errors_count"]
    if validation_errors_count > 0:
        validation_errors = context["validation_errors"]
        raise ValidationError(validation_errors_count, validation_errors)


def convert_spreadsheet_file(
    working_dir, schema_360, original_file_path, json_file_name, file_type
):
    context = {"file_type": file_type}

    lib_cove_config = LibCoveConfig()
    lib_cove_config.config.update(COVE_CONFIG)

    # Enable internal request cache within lib-cove
    lib_cove_config.config["cache_all_requests"] = True

    context.update(
        convert_spreadsheet(
            working_dir,
            "null",  # upload url (not needed)
            original_file_path,
            file_type,
            lib_cove_config,
            schema_360.schema_file,
            schema_360.pkg_schema_file,
        )
    )

    # Check for any schema extension
    with open(context["converted_path"], encoding="utf-8") as fp:
        json_data = json.load(fp, parse_float=Decimal)

        if extension_metadatas := schema_360.resolve_extension(json_data):
            # Delete old coverted data
            os.unlink(context["converted_path"])
            # Re-convert using the newly resolve_extension
            context.update(
                convert_spreadsheet(
                    working_dir,
                    "null",  # upload url (not needed)
                    original_file_path,
                    file_type,
                    lib_cove_config,
                    schema_360.schema_file,
                    schema_360.pkg_schema_file,
                )
            )
            context["extension_metadatas"] = extension_metadatas

    shutil.move(context["converted_path"], json_file_name)


def fetch_and_convert(args, dataset, schema_path, schema_package_path):
    """Fetches and converts 360 Giving datasets. Must return a dataset"""

    working_dir = os.path.join(args.data_dir, "validation", dataset["identifier"])
    working_dir = os.path.abspath(working_dir)
    os.makedirs(working_dir)

    # schema_360 is per file due to possible schema extensions being present

    schema_360 = Schema360(
        working_dir,
        local_pkg_schema_path=schema_package_path,
        local_grant_schema_path=schema_path,
    )

    # If we're only fetching particular publishers filter here
    if args.publisher_prefixes:
        if dataset["publisher"]["prefix"] not in args.publisher_prefixes:
            dataset["datagetter_metadata"] = {"downloads": False}
            return dataset

    try:
        res = None

        metadata = dataset.get("datagetter_metadata", {})
        dataset["datagetter_metadata"] = metadata

        if not dataset["license"] in acceptable_licenses + unacceptable_licenses:
            raise ValueError("Unrecognised license " + dataset["license"])

        url = dataset["distribution"][0]["downloadURL"]

        metadata["datetime_downloaded"] = strict_rfc3339.now_to_rfc3339_localoffset()

        try:
            print("Fetching %s" % url)
            res = session.get(
                url,
                headers={
                    "User-Agent": "datagetter (https://github.com/ThreeSixtyGiving/datagetter)"
                },
            )
            res.raise_for_status()

            metadata["downloads"] = True
        except Exception as e:
            if isinstance(e, KeyboardInterrupt):
                raise

            print(
                "\n\nDownload {} failed for dataset {}\n".format(
                    url, dataset["identifier"]
                )
            )
            traceback.print_exc()
            metadata["downloads"] = False
            metadata["error"] = str(e)

            if not isinstance(e, requests.exceptions.HTTPError):
                return dataset

        content_type = res.headers.get("content-type", "").split(";")[0].lower()
        file_type = None

        if content_type and content_type in CONTENT_TYPE_MAP:
            file_type = CONTENT_TYPE_MAP[content_type]
        elif "content-disposition" in res.headers:
            # When webserver serves file as an attachment rather than direct download
            # We need to parse the header to get the filename and filetype.
            # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Disposition
            content_disposition = res.headers.get("content-disposition")
            filename = dict(
                email.headerregistry.parser.parse_content_disposition_header(
                    content_disposition
                ).params
            ).get("filename")
            if filename:
                file_type = filename.split(".")[-1]

        # Last resort to guessing the file type
        if not file_type:
            file_type = url.split(".")[-1]
        if file_type not in CONTENT_TYPE_MAP.values():
            print(f"Unrecognised file type {file_type}")
            return dataset

        # Check that the downloaded json file is valid json and not junk from the webserver
        # e.g. a 500 error being output without the proper status code.
        if file_type == "json":
            try:
                json.loads(res.text)
            except ValueError:
                print("Warning: JSON file provided by webserver is invalid")
                metadata["downloads"] = False
                metadata["error"] = "Invalid JSON file provided by webserver"
                return dataset

        metadata["file_type"] = file_type

        original_file_path = os.path.join(
            args.data_dir, "original", f"{dataset['identifier']}.{file_type}"
        )

        with open(original_file_path, "wb") as fp:
            fp.write(res.content)

        json_file_name = os.path.join(
            args.data_dir, "json_all", f"{dataset['identifier']}.json"
        )

        metadata["file_size"] = os.path.getsize(original_file_path)

        if file_type == "json":
            os.link(original_file_path, json_file_name)
            metadata["json"] = json_file_name
        else:
            # Convert spreadsheet to JSON and cache the conversion
            try:
                print(f"Running convert on {original_file_path} to {json_file_name}")

                try:
                    # Hash the file
                    file_hash_str = cache.hash_file(original_file_path)
                    # Check if we have already converted the file
                    cached_file_path = cache.get_file(file_hash_str)

                    # We have converted the file before so copy from the CACHE_DIR
                    if cached_file_path:
                        try:
                            shutil.copy(cached_file_path, json_file_name)
                            print("Cache hit")
                        except (FileNotFoundError, PermissionError):
                            cached_file_path = False
                except cache.DatagetterCacheError as e:
                    print(f"Continuing without cache (hash/get): {e}")
                    cached_file_path = False

                if not cached_file_path:
                    convert_spreadsheet_file(
                        working_dir,
                        schema_360,
                        original_file_path,
                        json_file_name,
                        file_type,
                    )

                    try:
                        cache.update_cache(
                            json_file_name,
                            file_hash_str,
                            dataset["identifier"],
                            file_type,
                        )
                    except cache.DatagetterCacheError as e:
                        print(f"Continuing without cache (update error): {e}")

            except KeyboardInterrupt:
                raise
            except Exception:
                print(f"Warning: Unflattening failed for file {original_file_path}")
                traceback.print_exc()
                metadata["json"] = None
                metadata["valid"] = False
                metadata["error"] = "Could not unflatten file"
            else:
                metadata["json"] = json_file_name

        metadata["acceptable_license"] = dataset["license"] in acceptable_licenses

        # We can only do continue with the JSON if it did successfully convert.
        if metadata.get("json"):
            try:
                with open(json_file_name, "r") as fp:
                    data = json.load(fp)
                    validate(working_dir, schema_360, data)
            except ValidationError as e:
                print(
                    f"Warning: File {json_file_name} does not conform to 360Giving standard"
                )
                # Non-standard data breaks tools so get rid of it
                metadata["json"] = None
                metadata["valid"] = False
                metadata["error"] = "File does not conform to the 360Giving standard"
                print(e)
                # print(json.dumps(e.errors, indent=4))
            else:
                metadata["valid"] = True

            if metadata["valid"]:
                os.link(
                    json_file_name,
                    "{}/json_valid/{}.json".format(
                        args.data_dir, dataset["identifier"]
                    ),
                )
                data_valid.append(dataset)
                if metadata["acceptable_license"]:
                    os.link(
                        json_file_name,
                        "{}/json_acceptable_license_valid/{}.json".format(
                            args.data_dir, dataset["identifier"]
                        ),
                    )
                    data_acceptable_license_valid.append(dataset)

            if metadata["acceptable_license"]:
                os.link(
                    json_file_name,
                    "{}/json_acceptable_license/{}.json".format(
                        args.data_dir, dataset["identifier"]
                    ),
                )
                data_acceptable_license.append(dataset)

    # Exception catcher if /anything/ went wrong in fetch_and_convert function
    # we don't want to crash out
    except Exception as e:
        metadata["valid"] = False
        metadata["downloads"] = False
        metadata["json"] = None
        print(f"Unknown issue with {url} {e}")

    return dataset


def file_cache(url):
    res = session.get(url)
    res.raise_for_status()

    tmp_dir = tempfile.mkdtemp()
    out_file = os.path.join(tmp_dir, os.path.basename(url))

    print(f"Caching {url} to {out_file}")

    with open(out_file, "w") as fp:
        fp.write(res.text)

    return out_file


def get(args):
    schema_path = file_cache(
        f"https://raw.githubusercontent.com/ThreeSixtyGiving/standard/{args.schema_branch}/schema/360-giving-schema.json"
    )
    schema_package_path = file_cache(
        f"https://raw.githubusercontent.com/ThreeSixtyGiving/standard/{args.schema_branch}/schema/360-giving-package-schema.json"
    )

    try:
        cache.setup_database()
        cache.setup_cache_dir()
    except cache.DatagetterCacheError as e:
        print(e)
        print("Continuing without cache")

    if args.local_registry:
        mkdirs(args.data_dir, False)
        with open(args.local_registry) as fp:
            data_all = json.load(fp)
    else:
        mkdirs(args.data_dir, False)

        # Try the registry 5 times to get valid data.json output
        # This guards against temporary downtime or other issues that the
        # registry might experience fetching the data.
        for i in range(0, 5):
            try:
                res = session.get("https://registry.threesixtygiving.org/data.json")

                data_all = res.json()
                if len(data_all) > 0:
                    with open("%s/data_original.json" % args.data_dir, "w") as fp:
                        fp.write(res.text)
                    break
            except json.JSONDecodeError:
                print("Warning: Registry JSON data error, retrying in 1 second...")
                time.sleep(1)
                continue

    if args.limit_downloads:
        data_all = data_all[: args.limit_downloads]
        if args.publisher_prefixes:
            print(
                "Warning: Limit applied and publisher prefixes selected, can have one or the other not both."
            )
            exit(1)

    with Pool(args.threads) as process_pool:
        new_data_all = []
        # We iterate through data_all and return the object back with
        # some datagetter_metadata added
        data_metadata = process_pool.starmap(
            fetch_and_convert,
            zip(
                itertools.repeat(args),
                data_all,
                itertools.repeat(schema_path),
                itertools.repeat(schema_package_path),
            ),
        )

        # Extra guard against "None" getting added to this list from an exception or
        # rogue return
        if data_metadata:
            new_data_all += data_metadata

    # Output data.json after every dataset, to help with debugging if we fail
    # part way through
    with open("%s/data_all.json" % args.data_dir, "w") as fp:
        json.dump(new_data_all, fp, indent=4)
    with open("%s/data_valid.json" % args.data_dir, "w") as fp:
        json.dump(data_valid, fp, indent=4)
    with open("%s/data_acceptable_license.json" % args.data_dir, "w") as fp:
        json.dump(data_acceptable_license, fp, indent=4)
    with open("%s/data_acceptable_license_valid.json" % args.data_dir, "w") as fp:
        json.dump(data_acceptable_license_valid, fp, indent=4)
