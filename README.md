# mopidy-pandora

[![Latest PyPI version](https://img.shields.io/pypi/v/mopidy-pandora)](https://pypi.org/p/mopidy-pandora)
[![CI build status](https://img.shields.io/github/actions/workflow/status/mopidy/mopidy-pandora/ci.yml)](https://github.com/mopidy/mopidy-pandora/actions/workflows/ci.yml)
[![Test coverage](https://img.shields.io/codecov/c/gh/mopidy/mopidy-pandora)](https://codecov.io/gh/mopidy/mopidy-pandora)

[Mopidy](https://mopidy.com/) extension for playing music from [Pandora](https://pandora.com/).


## Maintainer wanted

I no longer have access to the Pandora music service in the region that I live,
which has made maintaining this project impossible. mopidy-pandora is looking
for a new maintainer, preferably someone who is familiar with the codebase,
familiar with Python development, and uses the paid Pandora subscription service
on a regular basis.

If you're interested, please take a look at the code base and work on submitting
a pull request or two to show you understand how everything works together.


## Features

- Support for both Pandora Premium and ad-supported free accounts.
- Add ratings to tracks (thumbs up, thumbs down, sleep, etc.).
- Bookmark songs or artists.
- Browse and add genre stations.
- Search for song, artist, and genre stations.
- Play QuickMix stations.
- Sort stations alphabetically or by date added.
- Delete stations from the user's Pandora profile.
- Scrobbling to Last.fm using [mopidy-scrobbler](https://github.com/mopidy/mopidy-scrobbler).


## Usage

Ideally, Mopidy needs [dynamic
playlists](https://github.com/mopidy/mopidy/issues/620) and [core
extensions](https://github.com/mopidy/mopidy/issues/1100) to properly support
Pandora. In the meantime, mopidy-pandora comes bundled with a frontend extension
that automatically adds more tracks to the tracklist as needed. mopidy-pandora
will ensure that there are always just two tracks in the tracklist: the
currently playing track and the track that is up next. It is not possible to mix
Pandora and non-Pandora tracks for playback at the same time, so any non-Pandora
tracks will be removed from the tracklist when playback starts.

Pandora expects users to interact with tracks at the point in time and in the
sequence that it serves them up. For this reason, trying to save tracks to
playlists or messing with the Mopidy-Pandora generated tracklist is probably not
a good idea. And not recommended.


## Dependencies

Requires a Pandora user account. Users with a Pandora Premium subscription will
have access to the higher quality 192 Kbps audio stream. Free accounts will play
advertisements.


## Installation

Install by running:

```sh
python3 -m pip install mopidy-pandora
```

See https://mopidy.com/ext/pandora/ for alternative installation methods.


## Configuration

Before starting Mopidy, you must add your Pandora username and password to your
Mopidy configuration file. The minimum configuration also requires that you
provide the details of the JSON API endpoint that you would like to use:

```ini
[pandora]
enabled = true
api_host = tuner.pandora.com/services/json/
partner_encryption_key =
partner_decryption_key =
partner_username = android
partner_password =
partner_device = android-generic
username =
password =
```

The following configuration values are available:

- `pandora/enabled`: If the Pandora extension should be enabled or not. Defaults
  to `true`.

- `pandora/api_host`: Which of the JSON API `endpoints
  <https://6xq.net/pandora-apidoc/json/>`_ to use. Note that the endpoints are
  different for Pandora Premium and free accounts (details in the link
  provided).

- `pandora/partner_*` related values: The
  [credentials](https://6xq.net/playground/pandora-apidoc/json/partners/#partners)
  to use for the Pandora API entry point. You *must* provide these values based
  on your device preferences.

- `pandora/username`: Your Pandora username. You *must* provide this.

- `pandora/password`: Your Pandora password. You *must* provide this.

- `pandora/preferred_audio_quality`: can be one of `lowQuality`,
  `mediumQuality`, or ``highQuality`` (default). If the preferred audio quality
  is not available for the partner device specified, then the next-lowest
  bitrate stream that Pandora supports for the chosen device will be used. Note
  that this setting has no effect for partner device types that only provide one
  audio stream (notably credentials associated with iOS). In such instances,
  mopidy-pandora will always revert to the default stream provided by the
  Pandora server.

- `pandora/sort_order`: defaults to `a-z`. Use `date` to display the list of
  stations in the order that the stations were added.

- `pandora/auto_setup`: Specifies if Mopidy-Pandora should automatically
  configure the Mopidy player for best compatibility with the Pandora radio
  stream. Defaults to `true` and turns `consume` on and `repeat`, `random`, and
  `single` modes off.

- `pandora/cache_time_to_live`: Specifies the length of time (in seconds) that
  station and genre lists should be cached for between automatic refreshes.
  Using a local cache greatly speeds up browsing the library. It should not be
  necessary to fiddle with this unless the Mopidy frontend that you are using
  does not support manually refreshing the library, and you want mopidy-pandora
  to immediately detect changes to your Pandora user profile that are made in
  other Pandora players. Setting this to `0` will disable caching completely
  and ensure that the latest lists are always retrieved directly from the
  Pandora server. Defaults to `86400` (i.e. 24 hours).

It is also possible to apply Pandora ratings and perform other actions on the
currently playing track using the standard pause/play/previous/next buttons.

- `pandora/event_support_enabled`: Setting this to `true` will enable the event
  triggers. Event support is disabled by default as this is still an
  experimental feature, and not something that is provided for in the Mopidy
  API. It works, but it is not impossible that the wrong events may be triggered
  for tracks or (in the worst case scenario) that one of your stations may be
  deleted accidentally. Mileage may vary - **use at your own risk.**
  
- `pandora/double_click_interval`: Successive button clicks that occur within
  this interval will trigger an event. Defaults to `2.50` seconds.
  
- `pandora/on_pause_resume_click`: Click pause and then play while a song is
  playing to trigger the event. Defaults to `thumbs_up`.
  
- `pandora/on_pause_next_click`: Click pause and then next in quick succession.
  Calls event and skips to next song. Defaults to `thumbs_down`.
  
- `pandora/on_pause_previous_click`: Click pause and then previous in quick
  succession. Calls event and restarts the current song. Defaults to `sleep`.
  
- `pandora/on_pause_resume_pause_click`: Click pause, resume, and pause again in
  quick succession (i.e. triple click). Calls event. Defaults to
  `delete_station`.

The full list of supported events are: `thumbs_up`, `thumbs_down`, `sleep`,
`add_artist_bookmark`, `add_song_bookmark`, and `delete_station`.


## Project resources

- [Source code](https://github.com/mopidy/mopidy-pandora)
- [Issues](https://github.com/mopidy/mopidy-pandora/issues)
- [Releases](https://github.com/mopidy/mopidy-pandora/releases)


## Development

### Set up development environment

Clone the repo using, e.g. using [gh](https://cli.github.com/):

```sh
gh repo clone mopidy/mopidy-pandora
```

Enter the directory, and install dependencies using [uv](https://docs.astral.sh/uv/):

```sh
cd mopidy-pandora/
uv sync
```

### Running tests

To run all tests and linters in isolated environments, use
[tox](https://tox.wiki/):

```sh
tox
```

To only run tests, use [pytest](https://pytest.org/):

```sh
pytest
```

To format the code, use [ruff](https://docs.astral.sh/ruff/):

```sh
ruff format .
```

To check for lints with ruff, run:

```sh
ruff check .
```

To check for type errors, use [pyright](https://microsoft.github.io/pyright/):

```sh
pyright .
```

### Making a release

To make a release to PyPI, go to the project's [GitHub releases
page](https://github.com/mopidy/mopidy-pandora/releases)
and click the "Draft a new release" button.

In the "choose a tag" dropdown, select the tag you want to release or create a
new tag, e.g. `v0.1.0`. Add a title, e.g. `v0.1.0`, and a description of the changes.

Decide if the release is a pre-release (alpha, beta, or release candidate) or
should be marked as the latest release, and click "Publish release".

Once the release is created, the `release.yml` GitHub Action will automatically
build and publish the release to
[PyPI](https://pypi.org/project/mopidy-pandora/).


## Credits

- Original author: [Andrew Wason](https://github.com/rectalogic)
- Previous maintainer: [John Cass](https://github.com/jcass77)
- Current maintainer: None. Maintainer wanted, see section above.
- [Contributors](https://github.com/mopidy/mopidy-pandora/graphs/contributors)
