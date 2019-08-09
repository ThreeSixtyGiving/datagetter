# 360Giving datagetter
Scripts to download the data from the http://data.threesixtygiving.org registry

## Install

Install dependencies:

```
# This script creates a new python virtual envionment and installs requirements.txt
$ ./update_requirements.sh
```
Or manually
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
