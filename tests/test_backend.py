from __future__ import absolute_import, division, print_function, unicode_literals

import mock

from mopidy import backend as backend_api
from mopidy import models

from pandora import APIClient, BaseAPIClient
from pandora.errors import PandoraException

from mopidy_pandora import client, library, playback
from mopidy_pandora.backend import PandoraBackend
from mopidy_pandora.library import PandoraLibraryProvider
from tests.conftest import get_backend


def test_uri_schemes(config):
    backend = get_backend(config)

    assert 'pandora' in backend.uri_schemes


def test_init_sets_up_the_providers(config):
    backend = get_backend(config)

    assert isinstance(backend.api, client.MopidyAPIClient)

    assert isinstance(backend.library, library.PandoraLibraryProvider)
    assert isinstance(backend.library, backend_api.LibraryProvider)

    assert isinstance(backend.playback, playback.PandoraPlaybackProvider)
    assert isinstance(backend.playback, backend_api.PlaybackProvider)


def test_end_of_tracklist_reached_prepares_next_track(config):
    backend = get_backend(config)

    backend.prepare_next_track = mock.Mock()
    backend.end_of_tracklist_reached('id_token_mock', False)
    backend.prepare_next_track.assert_called_with('id_token_mock', False)


def test_event_triggered_processes_event(config):
    backend = get_backend(config)

    backend.process_event = mock.Mock()
    backend.event_triggered('pandora:track:id_token_mock:id_token_mock', 'thumbs_up')
    backend.process_event.assert_called_with('pandora:track:id_token_mock:id_token_mock', 'thumbs_up')


def test_init_sets_preferred_audio_quality(config):
    config['pandora']['preferred_audio_quality'] = 'lowQuality'
    backend = get_backend(config)

    assert backend.api.default_audio_quality == BaseAPIClient.LOW_AUDIO_QUALITY


def test_on_start_logs_in(config):
    backend = get_backend(config)

    login_mock = mock.Mock()
    backend.api.login = login_mock
    backend.on_start()

    backend.api.login.assert_called_once_with('john', 'smith')


def test_prepare_next_track_triggers_event(config):
    with mock.patch.object(PandoraLibraryProvider,
                           'get_next_pandora_track',
                           mock.Mock()) as get_next_pandora_track_mock:

        backend = get_backend(config)

        backend.prepare_next_track('id_token_mock')
        track = models.Ref.track(name='name_mock', uri='pandora:track:id_token_mock:id_token_mock')
        get_next_pandora_track_mock.return_value = track
        backend._trigger_next_track_available = mock.Mock()
        backend.end_of_tracklist_reached()

        backend._trigger_next_track_available.assert_called_with(track, False)


def test_process_event_calls_method(config, caplog):
    with mock.patch.object(PandoraLibraryProvider, 'lookup_pandora_track', mock.Mock()):
        with mock.patch.object(APIClient, '__call__', mock.Mock()) as mock_call:

            backend = get_backend(config)
            uri_mock = 'pandora:track:id_token_mock:id_token_mock'
            backend._trigger_event_processed = mock.Mock()

            for event in ['thumbs_up', 'thumbs_down', 'sleep', 'add_artist_bookmark',
                          'add_song_bookmark', 'delete_station']:

                if event == 'delete_station':
                    backend.library.refresh = mock.Mock()
                    backend.library.browse = mock.Mock()

                backend.process_event(uri_mock, event)

                assert mock_call.called
                mock_call.reset_mock()
                backend._trigger_event_processed.assert_called_with(uri_mock, event)
                backend._trigger_event_processed.reset_mock()

                assert "Triggering event '{}'".format(event) in caplog.text()


def test_process_event_handles_pandora_exception(config, caplog):
    with mock.patch.object(PandoraLibraryProvider, 'lookup_pandora_track', mock.Mock()):
        with mock.patch.object(PandoraBackend, 'thumbs_up', mock.Mock()) as mock_call:

            backend = get_backend(config)
            uri_mock = 'pandora:track:id_token_mock:id_token_mock'
            backend._trigger_event_processed = mock.Mock()
            mock_call.side_effect = PandoraException('exception_mock')

            assert not backend.process_event(uri_mock, 'thumbs_up')
            mock_call.assert_called_with(uri_mock)
            assert not backend._trigger_event_processed.called

            assert 'Error calling Pandora event: thumbs_up.' in caplog.text()
