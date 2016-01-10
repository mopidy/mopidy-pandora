from __future__ import absolute_import, unicode_literals

import unittest

import mock

from mopidy import models

import mopidy_pandora.listener as listener


class PandoraFrontendListenerTest(unittest.TestCase):

    def setUp(self):  # noqa: N802
        self.listener = listener.PandoraFrontendListener()

    def test_on_event_forwards_to_specific_handler(self):
        self.listener.end_of_tracklist_reached = mock.Mock()

        self.listener.on_event(
            'end_of_tracklist_reached', station_id='id_mock', auto_play=False)

        self.listener.end_of_tracklist_reached.assert_called_with(station_id='id_mock', auto_play=False)

    def test_listener_has_default_impl_for_end_of_tracklist_reached(self):
        self.listener.end_of_tracklist_reached(station_id='id_mock', auto_play=False)


class PandoraEventHandlingFrontendListenerTest(unittest.TestCase):

    def setUp(self):  # noqa: N802
        self.listener = listener.PandoraEventHandlingFrontendListener()

    def test_on_event_forwards_to_specific_handler(self):
        self.listener.event_triggered = mock.Mock()

        self.listener.on_event('event_triggered', track_uri='pandora:track:id_mock:token_mock',
                               pandora_event='event_mock')

        self.listener.event_triggered.assert_called_with(track_uri='pandora:track:id_mock:token_mock',
                                                         pandora_event='event_mock')

    def test_listener_has_default_impl_for_event_triggered(self):
        self.listener.event_triggered('pandora:track:id_mock:token_mock', 'event_mock')


class PandoraBackendListenerTest(unittest.TestCase):

    def setUp(self):  # noqa: N802
        self.listener = listener.PandoraBackendListener()

    def test_on_event_forwards_to_specific_handler(self):
        self.listener.next_track_available = mock.Mock()

        self.listener.on_event(
            'next_track_available', track=models.Ref(name='name_mock'), auto_play=False)

        self.listener.next_track_available.assert_called_with(track=models.Ref(name='name_mock'), auto_play=False)

    def test_listener_has_default_impl_for_next_track_available(self):
        self.listener.next_track_available(track=models.Ref(name='name_mock'), auto_play=False)

    def test_listener_has_default_impl_for_event_processed(self):
        self.listener.event_processed(track_uri='pandora:track:id_mock:token_mock',
                                      pandora_event='event_mock')


class PandoraPlaybackListenerTest(unittest.TestCase):

    def setUp(self):  # noqa: N802
        self.listener = listener.PandoraPlaybackListener()

    def test_on_event_forwards_to_specific_handler(self):
        self.listener.track_changed = mock.Mock()

        self.listener.on_event(
            'track_changed', track=models.Ref(name='name_mock'))

        self.listener.track_changed.assert_called_with(track=models.Ref(name='name_mock'))

    def test_listener_has_default_impl_for_track_changed(self):
        self.listener.track_changed(track=models.Ref(name='name_mock'))

    def test_listener_has_default_impl_for_track_unplayable(self):
        self.listener.track_unplayable(track=models.Ref(name='name_mock'))

    def test_listener_has_default_impl_for_skip_limit_exceeded(self):
        self.listener.skip_limit_exceeded()
