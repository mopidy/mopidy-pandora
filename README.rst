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
    api_host = tuner.pandora.com/services/json/
    partner_encryption_key = 
    partner_decryption_key = 
    partner_username = iphone
    partner_password = 
    partner_device = IP01
    preferred_audio_quality = mediumQuality
    username = 
    password = 

The **api_host** and **partner_** keys can be obtained from:

 `pandora-apidoc <http://6xq.net/playground/pandora-apidoc/json/partners/#partners>`_

**preferred_audio_quality** can be one of 'lowQuality', 'mediumQuality' (default), or 'highQuality'. If the preferred
audio quality is not available for the partner device specified, then the next-highest bitrate stream that Pandora
supports for the chosen device will be used.

Usage
=====

Mopidy needs `dynamic playlist <https://github.com/mopidy/mopidy/issues/620>`_ support to properly support Pandora.
In the meantime, Mopidy-Pandora represents each Pandora station as a single track playlist.
Play this track in repeat mode and each time it is played, the next dynamic track in that station will be played.


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
