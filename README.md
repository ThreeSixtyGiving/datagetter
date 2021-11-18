# 360Giving datagetter
Scripts to download the data from the http://data.threesixtygiving.org registry

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

Run:
```
# See datagetter.py --help for options
$ datagetter.py
```

## Developers

If you are updating `requirements.txt` please make sure you use version 3.8 of Python.
