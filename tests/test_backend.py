from __future__ import unicode_literals

import mock

from mopidy import backend as backend_api

from pandora import BaseAPIClient

from mopidy_pandora import client, library, playback
from tests.conftest import get_backend, request_exception_mock


def test_uri_schemes(config):
    backend = get_backend(config)

    assert 'pandora' in backend.uri_schemes


def test_init_sets_up_the_providers(config):
    backend = get_backend(config)

    assert isinstance(backend.api, client.MopidyPandoraAPIClient)

    assert isinstance(backend.library, library.PandoraLibraryProvider)
    assert isinstance(backend.library, backend_api.LibraryProvider)

    assert isinstance(backend.playback, playback.PandoraPlaybackProvider)
    assert isinstance(backend.playback, backend_api.PlaybackProvider)


def test_init_sets_preferred_audio_quality(config):
    config['pandora']['preferred_audio_quality'] = 'lowQuality'
    backend = get_backend(config)

    assert backend.api.default_audio_quality == BaseAPIClient.LOW_AUDIO_QUALITY


def test_playback_provider_selection_ratings_disabled(config):
    config['pandora']['ratings_support_enabled'] = 'false'
    backend = get_backend(config)

    assert isinstance(backend.playback, playback.PandoraPlaybackProvider)


def test_playback_provider_selection_ratings_default(config):
    config['pandora']['ratings_support_enabled'] = ''
    backend = get_backend(config)

    assert isinstance(backend.playback, playback.PandoraPlaybackProvider)


def test_playback_provider_selection_ratings_enabled(config):
    config['pandora']['ratings_support_enabled'] = 'true'
    backend = get_backend(config)

    assert isinstance(backend.playback, playback.RatingsSupportPlaybackProvider)


def test_on_start_logs_in(config):
    backend = get_backend(config)

    login_mock = mock.PropertyMock()
    backend.api.login = login_mock
    backend.on_start()

    backend.api.login.assert_called_once_with('john', 'doe')


def test_on_start_handles_request_exception(config, caplog):
    backend = get_backend(config, True)

    backend.api.login = request_exception_mock
    backend.on_start()

    # Check that request exceptions are caught and logged
    assert 'Error logging in to Pandora' in caplog.text()