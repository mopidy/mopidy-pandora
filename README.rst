**************
Mopidy-Pandora
**************

.. image:: https://img.shields.io/pypi/v/Mopidy-Pandora.svg?style=flat
    :target: https://pypi.python.org/pypi/Mopidy-Pandora/
    :alt: Latest PyPI version

.. image:: https://img.shields.io/pypi/dm/Mopidy-Pandora.svg?style=flat
    :target: https://pypi.python.org/pypi/Mopidy-Pandora/
    :alt: Number of PyPI downloads

.. image:: https://img.shields.io/travis/rectalogic/mopidy-pandora/develop.svg?style=flat
    :target: https://travis-ci.org/rectalogic/mopidy-pandora
    :alt: Travis CI build status

.. image:: https://img.shields.io/coveralls/rectalogic/mopidy-pandora/develop.svg?style=flat
   :target: https://coveralls.io/r/rectalogic/mopidy-pandora?branch=develop
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
    preferred_audio_quality = highQuality
    username =
    password =
    sort_order = date
    auto_setup = true

    ### EXPERIMENTAL EVENT HANDLING IMPLEMENTATION ###
    event_support_enabled = false
    double_click_interval = 2.00
    on_pause_resume_click = thumbs_up
    on_pause_next_click = thumbs_down
    on_pause_previous_click = sleep

The **api_host** and **partner_** keys can be obtained from:

 `pandora-apidoc <http://6xq.net/playground/pandora-apidoc/json/partners/#partners>`_

**preferred_audio_quality** can be one of 'lowQuality', 'mediumQuality', or 'highQuality' (default). If the preferred
audio quality is not available for the partner device specified, then the next-lowest bitrate stream that Pandora
supports for the chosen device will be used.

**sort_order** defaults to the date that the station was added. Use 'A-Z' to display the list of stations in
alphabetical order.

**EXPERIMENTAL EVENT HANDLING IMPLEMENTATION:** use these settings to work around the limitations of the current Mopidy core
and web extensions:

- double_click_interval - successive button clicks that occur within this interval (in seconds) will trigger the event.
- on_pause_resume_click - click pause and then play while a song is playing to trigger the event.
- on_pause_next_click - click pause and then next in quick succession. Calls event and skips to next song.
- on_pause_previous_click - click pause and then previous in quick succession. Calls event and skips to next song.

The supported events are: thumbs_up, thumbs_down, sleep, add_artist_bookmark, add_song_bookmark

Usage
=====

Mopidy needs `dynamic playlist <https://github.com/mopidy/mopidy/issues/620>`_ and
`core extensions <https://github.com/mopidy/mopidy/issues/1100>`_ support to properly support Pandora. In the meantime,
Mopidy-Pandora represents each Pandora station as a separate playlist. The Playlist needs to be played **in repeat mode**
and **consume**, **random**, and **single** should be turned off. Mopidy-Pandora will set this up automatically unless
you set the **auto_setup** config parameter to 'false'.

Each time a track is played, the next dynamic track for that Pandora station will be played. The playlist will consist
of a single track unless the experimental ratings support is enabled. With ratings support enabled, the playlist will
contain three tracks. These are just used to determine whether the user clicked on the 'previous' or 'next' playback
buttons, and all three tracks point to the same dynamic track for that Pandora station (i.e. it does not matter which
one you select to play).


Project resources
=================

- `Source code <https://github.com/rectalogic/mopidy-pandora>`_
- `Issue tracker <https://github.com/rectalogic/mopidy-pandora/issues>`_
- `Development branch tarball <https://github.com/rectalogic/mopidy-pandora/archive/develop.tar.gz#egg=Mopidy-Pandora-dev>`_


Changelog
=========

v0.1.8 (Jan 8, 2016)
----------------------------------------

- Update dependencies: requires at least pydora 1.5.1.

v0.1.7 (Oct 31, 2015)
----------------------------------------

- Configuration parameter 'auto_set_repeat' has been renamed to 'auto_setup' - please update your Mopidy configuration file.
- Now resumes playback after a track has been rated.
- Enhanced auto_setup routines to ensure that 'consume', 'random', and 'single' modes are disabled as well.
- Optimized auto_setup routines: now only called when the Mopidy tracklist changes.

v0.1.6 (Oct 26, 2015)
----------------------------------------

- Release to pypi

v0.1.5 (Aug 20, 2015)
----------------------------------------

- Add option to automatically set tracks to play in repeat mode when Mopidy-Pandora starts.
- Add experimental support for rating songs by re-using buttons available in the current front-end Mopidy extensions.
- Audio quality now defaults to the highest setting.
- Improved caching to revert to Pandora server if station cannot be found in the local cache.
- Fix to retrieve stations by ID instead of token.
- Add unit tests to increase test coverage.

v0.1.4 (Aug 17, 2015)
----------------------------------------

- Limit number of consecutive track skips to prevent Mopidy's skip-to-next-on-error behaviour from locking the user's Pandora account.
- Better handling of exceptions that occur in the backend to prevent Mopidy actor crashes.
- Add support for unicode characters in station and track names.

v0.1.3 (Jul 11, 2015)
----------------------------------------

- Update to work with release of Mopidy version 1.0
- Update to work with pydora version >= 1.4.0: now keeps the Pandora session alive in tha API itself.
- Implement station list caching to speed up browsing.
- Get rid of 'Stations' root directory. Browsing now displays all of the available stations immediately.
- Fill artist name to improve how tracks are displayed in various Mopidy front-end extensions.

v0.1.2 (Jun 20, 2015)
----------------------------------------

- Enhancement to handle 'Invalid Auth Token' exceptions when the Pandora session expires after long periods of
  inactivity. Allows Mopidy-Pandora to run indefinitely on dedicated music servers like the Pi MusicBox.
- Add configuration option to sort stations alphabetically, instead of by date.

v0.1.1 (Mar 22, 2015)
----------------------------------------

- Added ability to make preferred audio quality user-configurable.

v0.1.0 (Dec 28, 2014)
----------------------------------------

- Initial release.
