#!/usr/bin/env python3

from distutils.core import setup

install_requires = []

with open('./requirements.in') as requirements_txt:
    requirements = requirements_txt.read().strip().splitlines()
    for requirement in requirements:
        if requirement.startswith('#'):
            continue
        elif requirement.startswith('-e '):
            install_requires.append(requirement.split('=')[1])
        else:
            install_requires.append(requirement)

setup(
    name='datagetter',
    version='0.1.0',
    author='Open Data Services',
    author_email='contact@opendataservices.coop',
    scripts=['datagetter.py'],
    url='https://github.com/ThreeSixtyGiving/datagetter',
    license='LICENSE',
    description='Fetches the data from registry.threesixtygiving.org',
    install_requires=install_requires,
    packages=['getter'],
    packages_dir={'getter': 'getter'}
)
