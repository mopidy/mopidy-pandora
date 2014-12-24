****************************
Mopidy-Pandora
****************************

.. image:: https://img.shields.io/pypi/v/Mopidy-Pandora.svg?style=flat
    :target: https://pypi.python.org/pypi/Mopidy-Pandora/
    :alt: Latest PyPI version

.. image:: https://img.shields.io/pypi/dm/Mopidy-Pandora.svg?style=flat
    :target: https://pypi.python.org/pypi/Mopidy-Pandora/
    :alt: Number of PyPI downloads

.. image:: https://img.shields.io/travis/rectalogic/mopidy-pandora/master.png?style=flat
    :target: https://travis-ci.org/rectalogic/mopidy-pandora
    :alt: Travis CI build status

.. image:: https://img.shields.io/coveralls/rectalogic/mopidy-pandora/master.svg?style=flat
   :target: https://coveralls.io/r/rectalogic/mopidy-pandora?branch=master
   :alt: Test coverage

Mopidy extension for Pandora


Installation
============

Install by running::

    pip install Mopidy-Pandora

Or, if available, install the Debian/Ubuntu package from `apt.mopidy.com
<http://apt.mopidy.com/>`_.


Configuration
=============

Before starting Mopidy, you must add configuration for
Mopidy-Pandora to your Mopidy configuration file::

    [pandora]
    enabled = true
    partner_encryption_key = 
    partner_decryption_key = 
    partner_username = iphone
    partner_password = 
    partner_device = IP01
    username = 
    password = 

The **partner_** keys can be obtained from `pandora-apidoc <http://6xq.net/playground/pandora-apidoc/json/partners/#partners>`_

Project resources
=================

- `Source code <https://github.com/rectalogic/mopidy-pandora>`_
- `Issue tracker <https://github.com/rectalogic/mopidy-pandora/issues>`_
- `Development branch tarball <https://github.com/rectalogic/mopidy-pandora/archive/master.tar.gz#egg=Mopidy-Pandora-dev>`_


Changelog
=========

v0.1.0 (UNRELEASED)
----------------------------------------

- Initial release.
