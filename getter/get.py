import requests
import json
import flattentool
import os
import tempfile
import shutil
import traceback
import strict_rfc3339
import rfc6266  # (content-disposition header parser)
import itertools
from jsonschema import validate, ValidationError, FormatChecker
from multiprocessing.dummy import Pool

acceptable_licenses = [
    'http://www.opendefinition.org/licenses/odc-pddl',
    'https://creativecommons.org/publicdomain/zero/1.0/',
    'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/2/',
    'http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/',
    'https://creativecommons.org/licenses/by/4.0/',
    'https://creativecommons.org/licenses/by-sa/3.0/',
    'https://creativecommons.org/licenses/by-sa/4.0/',
]

unacceptable_licenses = [
    '',
    # Not relicenseable as CC-BY
    'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/1/', 
    'https://creativecommons.org/licenses/by-nc/4.0/',
    'https://creativecommons.org/licenses/by-nc-sa/4.0/',
]

CONTENT_TYPE_MAP = {
    'application/json': 'json',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
    'text/csv': 'csv'
}

schema = json.loads(requests.get('https://raw.githubusercontent.com/ThreeSixtyGiving/standard/master/schema/360-giving-package-schema.json').text)

data_valid = []
data_acceptable_license = []
data_acceptable_license_valid = []


def convert_spreadsheet(input_path, converted_path, file_type):
    encoding = 'utf-8-sig'
    if file_type == 'csv':
        tmp_dir = tempfile.mkdtemp()
        destination = os.path.join(tmp_dir, 'grants.csv')
        shutil.copy(input_path, destination)
        try:
            with open(destination, encoding='utf-8-sig') as main_sheet_file:
                main_sheet_file.read()
        except UnicodeDecodeError:
            try:
                with open(destination, encoding='cp1252') as main_sheet_file:
                    main_sheet_file.read()
                encoding = 'cp1252'
            except UnicodeDecodeError:
                encoding = 'latin_1'
        input_name = tmp_dir
    else:
        input_name = input_path
    flattentool.unflatten(
        input_name,
        output_name=converted_path,
        input_format=file_type,
        root_list_path='grants',
        root_id='',
        schema='https://raw.githubusercontent.com/ThreeSixtyGiving/standard/master/schema/360-giving-schema.json',
        convert_titles=True,
        encoding=encoding,
        metatab_schema='https://raw.githubusercontent.com/ThreeSixtyGiving/standard/master/schema/360-giving-package-schema.json',
        metatab_name='Meta',
        metatab_vertical_orientation=True,
    )


def mkdirs(data_dir):
    os.mkdir(data_dir)
    for dir_name in ['original', 'json_all', 'json_valid',
                     'json_acceptable_license',
                     'json_acceptable_license_valid']:
        os.mkdir("%s/%s" % (data_dir, dir_name))


def fetch_and_convert(args, dataset):
    r = None

    metadata = dataset.get('datagetter_metadata', {})
    dataset['datagetter_metadata'] = metadata

    if not dataset['license'] in acceptable_licenses + unacceptable_licenses:
        raise ValueError('Unrecognised license '+dataset['license'])

    url = dataset['distribution'][0]['downloadURL']

    if args.download:
        proxies = None
        metadata['datetime_downloaded'] = strict_rfc3339.now_to_rfc3339_localoffset()
        if args.socks5_proxy:
            proxies = {
                'http': args.socks5_proxy,
                'https': args.socks5_proxy,
            }

        try:
            print("Fetching %s" % url)
            r = requests.get(
                url,
                headers={'User-Agent': 'datagetter (https://github.com/ThreeSixtyGiving/datagetter)'},
                proxies=proxies
            )
            r.raise_for_status()

            metadata['downloads'] = True
        except Exception as e:
            if isinstance(e, KeyboardInterrupt):
                raise

            print("\n\nDownload failed for dataset {}\n".format(dataset['identifier']))
            traceback.print_exc()
            metadata['downloads'] = False
            metadata['error'] = str(e)

            if not isinstance(e, requests.exceptions.HTTPError):
                return

        content_type = r.headers.get('content-type', '').split(';')[0].lower()
        if content_type and content_type in CONTENT_TYPE_MAP:
            file_type = CONTENT_TYPE_MAP[content_type]
        elif 'content-disposition' in r.headers:
            file_type = rfc6266.parse_requests_response(r).filename_unsafe.split('.')[-1]
        else:
            file_type = url.split('.')[-1]
        if file_type not in CONTENT_TYPE_MAP.values():
            print("\n\nUnrecognised file type {}\n".format(file_type))
            return
        metadata['file_type'] = file_type
        file_name = args.data_dir+'/original/'+dataset['identifier']+'.'+file_type
        with open(file_name, 'wb') as fp:
            fp.write(r.content)
    else:
        file_type = metadata['file_type']
        file_name = args.data_dir+'/original/'+dataset['identifier']+'.'+file_type

    json_file_name = '{}/json_all/{}.json'.format(args.data_dir, dataset['identifier'])

    metadata['file_size'] = os.path.getsize(file_name)

    if args.convert and (
            args.convert_big_files or
            metadata['file_size'] < 10 * 1024 * 1024
            ):
        if file_type == 'json':
            os.link(file_name, json_file_name)
            metadata['json'] = json_file_name
        else:
            try:
                print("Running convert on %s to %s" % (file_name,
                                                       json_file_name))
                convert_spreadsheet(
                    file_name,
                    json_file_name,
                    file_type)
            except KeyboardInterrupt:
                raise
            except:
                print("\n\nUnflattening failed for file {}\n".format(file_name))
                traceback.print_exc()
                metadata['json'] = None
            else:
                metadata['json'] = json_file_name

    metadata['acceptable_license'] = dataset['license'] in acceptable_licenses

    # We can only do anything with the JSON if it did successfully convert.
    if metadata.get('json'):
        format_checker = FormatChecker()
        if args.validate:
            try:
                with open(json_file_name, 'r') as fp:
                    validate(json.load(fp), schema, format_checker=format_checker)
            except (ValidationError, ValueError):
                metadata['valid'] = False
            else:
                metadata['valid'] = True

        if metadata['valid']:
            os.link(json_file_name,
                    '{}/json_valid/{}.json'.format(args.data_dir, dataset['identifier']))
            data_valid.append(dataset)
            if metadata['acceptable_license']:
                os.link(json_file_name,
                        '{}/json_acceptable_license_valid/{}.json'.format(args.data_dir, dataset['identifier']))
                data_acceptable_license_valid.append(dataset)

        if metadata['acceptable_license']:
            os.link(json_file_name,
                    '{}/json_acceptable_license/{}.json'.format(args.data_dir, dataset['identifier']))
            data_acceptable_license.append(dataset)


def get(args):
    mkdirs(args.data_dir)

    if args.download:
        r = requests.get('http://data.threesixtygiving.org/data.json')
        with open('%s/data_original.json' % args.data_dir, 'w') as fp:
            fp.write(r.text)
        data_all = r.json()
    else:
        data_all = json.load(open('%s/data_all.json' % args.data_dir))

    with Pool(args.threads) as process_pool:
        process_pool.starmap(fetch_and_convert, zip(itertools.repeat(args),
                                                    data_all))

    # Output data.json after every dataset, to help with debugging if we fail
    # part way through
    with open('%s/data_all.json' % args.data_dir, 'w') as fp:
        json.dump(data_all, fp, indent=4)
    with open('%s/data_valid.json' % args.data_dir, 'w') as fp:
        json.dump(data_valid, fp, indent=4)
    with open('%s/data_acceptable_license.json' % args.data_dir, 'w') as fp:
        json.dump(data_acceptable_license, fp, indent=4)
    with open('%s/data_acceptable_license_valid.json' % args.data_dir, 'w') as fp:
        json.dump(data_acceptable_license_valid, fp, indent=4)
