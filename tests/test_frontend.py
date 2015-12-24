import unittest

from mopidy import core

from mopidy.models import Track

import pykka

from mopidy_pandora.frontend import PandoraFrontend

from tests import conftest, dummy_backend


class FrontendTest(unittest.TestCase):

    def setUp(self):  # noqa: N802
        config = {
            'core': {
                'max_tracklist_length': 10000,
            }
        }

        self.backend = dummy_backend.create_proxy()

        self.core = core.Core.start(
            config, backends=[self.backend]).proxy()

        self.tracks = [
            Track(uri='pandora:track:mock_id1:mock_token1', length=40000),
            Track(uri='pandora:track:mock_id2:mock_token2', length=40000),
            Track(uri='pandora:track:mock_id3:mock_token3', length=40000),  # Unplayable
            Track(uri='pandora:track:mock_id4:mock_token4', length=40000),
            Track(uri='pandora:track:mock_id5:mock_token5', length=None),   # No duration
        ]

        self.uris = [
            'pandora:track:mock_id1:mock_token1', 'pandora:track:mock_id2:mock_token2',
            'pandora:track:mock_id3:mock_token3', 'pandora:track:mock_id4:mock_token4',
            'pandora:track:mock_id5:mock_token5']

        def lookup(uris):
            result = {uri: [] for uri in uris}
            for track in self.tracks:
                if track.uri in result:
                    result[track.uri].append(track)
            return result

        self.core.library.lookup = lookup
        self.tl_tracks = self.core.tracklist.add(uris=self.uris).get()

    def tearDown(self):  # noqa: N802
        pykka.ActorRegistry.stop_all()

    def test_set_options_performs_auto_setup(self):
        self.core.tracklist.set_repeat(False).get()
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()

        frontend = PandoraFrontend.start(conftest.config(), self.core).proxy()
        frontend.track_playback_started(self.tracks[0]).get()
        assert self.core.tracklist.get_repeat().get() is True
        assert self.core.tracklist.get_consume().get() is False
        assert self.core.tracklist.get_random().get() is False
        assert self.core.tracklist.get_single().get() is False
