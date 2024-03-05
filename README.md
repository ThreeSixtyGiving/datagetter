# 360Giving datagetter
Scripts to download the data from the http://registry.threesixtygiving.org file registry

## Install

Install dependencies:

The datagetter is tested to run on python3.8

```
# Create a new python3 virtual environment
$ virtualenv --python python3 .ve
$ source .ve/bin/activate
# Install datagetter dependencies
$ pip install -r requirements.txt
```

If you want to install the datagetter on your environment (rather than run it from the source directory)
```
# see setup.py --help for more options
$ setup.py install
```


## Usage

Basic usage to download all published 360Giving data run:

```
$ datagetter.py
```

### See datagetter.py --help for more options

```

$ datagetter.py --help
usage: datagetter.py [-h] [--no-download] [--local-registry LOCAL_REGISTRY] [--no-convert] [--no-convert-big-files] [--no-validate] [--data-dir DATA_DIR] [--threads THREADS] [--socks5 SOCKS5_PROXY] [--limit-downloads LIMIT_DOWNLOADS] [--schema-branch SCHEMA_BRANCH]
                     [--publishers PUBLISHER_PREFIXES [PUBLISHER_PREFIXES ...]]

optional arguments:
  -h, --help            show this help message and exit
  --no-download         Don't download any files only convert existing data
  --local-registry LOCAL_REGISTRY
                        Use a local registry file rather than registry.threesixtygiving.org
  --no-convert
  --no-convert-big-files
  --no-validate
  --data-dir DATA_DIR
  --threads THREADS
  --socks5 SOCKS5_PROXY
                        Use a socks5 proxy to fetch publisher data. Example --socks5=socks5://host:port
  --limit-downloads LIMIT_DOWNLOADS
                        Limit the number of file downloads
  --schema-branch SCHEMA_BRANCH
                        Specify a git branch of the 360Giving schema
  --publishers PUBLISHER_PREFIXES [PUBLISHER_PREFIXES ...]
                        Only download for selected publishers
```

## Developers

If you are updating `requirements.txt` please make sure you use version 3.8 of Python.
