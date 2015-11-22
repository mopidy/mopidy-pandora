from mopidy import backend, core
from mopidy.internal import encoding

from pandora import BaseAPIClient, clientbuilder

import pykka

import requests

import rpc

from mopidy_pandora.client import MopidyPandoraAPIClient
from mopidy_pandora.library import PandoraLibraryProvider
from mopidy_pandora.playback import EventSupportPlaybackProvider, PandoraPlaybackProvider
from mopidy_pandora.uri import logger


class PandoraBackend(pykka.ThreadingActor, backend.Backend, core.CoreListener):

    def __init__(self, config, audio):
        super(PandoraBackend, self).__init__()
        self._config = config['pandora']
        settings = {
            "API_HOST": self._config.get("api_host", 'tuner.pandora.com/services/json/'),
            "DECRYPTION_KEY": self._config["partner_decryption_key"],
            "ENCRYPTION_KEY": self._config["partner_encryption_key"],
            "PARTNER_USER": self._config["partner_username"],
            "PARTNER_PASSWORD": self._config["partner_password"],
            "DEVICE": self._config["partner_device"],
            "AUDIO_QUALITY": self._config.get("preferred_audio_quality", BaseAPIClient.HIGH_AUDIO_QUALITY)
        }
        self.api = clientbuilder.SettingsDictBuilder(settings, client_class=MopidyPandoraAPIClient).build()

        self.library = PandoraLibraryProvider(backend=self, sort_order=self._config['sort_order'])

        self.auto_setup = self._config['auto_setup']
        self.setup_required = self.auto_setup

        self.rpc_client = rpc.RPCClient(config['http']['hostname'], config['http']['port'])

        self.supports_events = False
        if self._config['event_support_enabled']:
            self.supports_events = True
            self.playback = EventSupportPlaybackProvider(audio=audio, backend=self)
        else:
            self.playback = PandoraPlaybackProvider(audio=audio, backend=self)

        self.uri_schemes = ['pandora']

    def on_start(self):
        try:
            self.api.login(self._config["username"], self._config["password"])
        except requests.exceptions.RequestException as e:
            logger.error('Error logging in to Pandora: %s', encoding.locale_decode(e))

    def tracklist_changed(self):
        self.setup_required = self.auto_setup
