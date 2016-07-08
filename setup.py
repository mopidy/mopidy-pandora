from __future__ import unicode_literals

import re
import sys

from setuptools import find_packages, setup
from setuptools.command.test import test


def get_version(filename):
    with open(filename) as fh:
        metadata = dict(re.findall("__([a-z]+)__ = '([^']+)'", fh.read()))
        return metadata['version']


class Tox(test):
    user_options = [(b'tox-args=', b'a', "Arguments to pass to tox")]

    def initialize_options(self):
        test.initialize_options(self)
        self.tox_args = None

    def finalize_options(self):
        test.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # import here, cause outside the eggs aren't loaded
        import tox
        import shlex
        args = self.tox_args
        if args:
            args = shlex.split(self.tox_args)
        errno = tox.cmdline(args=args)
        sys.exit(errno)

setup(
    name='Mopidy-Pandora',
    version=get_version('mopidy_pandora/__init__.py'),
    url='https://github.com/rectalogic/mopidy-pandora',
    license='Apache License, Version 2.0',
    author='Andrew Wason',
    author_email='rectalogic@rectalogic.com',
    description='Mopidy extension for Pandora',
    long_description=open('README.rst').read(),
    packages=find_packages(exclude=['tests', 'tests.*']),
    zip_safe=False,
    include_package_data=True,
    install_requires=[
        'setuptools',
        'cachetools >= 1.0.0',
        'Mopidy >= 1.1.2',
        'Pykka >= 1.1',
        'pydora >= 1.7.3',
        'requests >= 2.5.0'
    ],
    tests_require=['tox'],
    cmdclass={'test': Tox},
    entry_points={
        'mopidy.ext': [
            'pandora = mopidy_pandora:Extension',
        ],
    },
    classifiers=[
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Topic :: Multimedia :: Sound/Audio :: Players',
    ],
)
