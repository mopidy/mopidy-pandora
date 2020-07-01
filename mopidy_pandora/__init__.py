import logging
import pathlib

import pkg_resources

from mopidy import config, ext

__version__ = pkg_resources.get_distribution("Mopidy-Pandora").version

logger = logging.getLogger(__name__)


class Extension(ext.Extension):

    dist_name = "Mopidy-Pandora"
    ext_name = "pandora"
    version = __version__

    def get_default_config(self):
        return config.read(pathlib.Path(__file__).parent / "ext.conf")

    def get_config_schema(self):
        from pandora.client import BaseAPIClient

        schema = super().get_config_schema()
        schema["api_host"] = config.String()
        schema["partner_encryption_key"] = config.String()
        schema["partner_decryption_key"] = config.String()
        schema["partner_username"] = config.String()
        schema["partner_password"] = config.String()
        schema["partner_device"] = config.String()
        schema["username"] = config.String()
        schema["password"] = config.Secret()
        schema["preferred_audio_quality"] = config.String(
            choices=[
                BaseAPIClient.LOW_AUDIO_QUALITY,
                BaseAPIClient.MED_AUDIO_QUALITY,
                BaseAPIClient.HIGH_AUDIO_QUALITY,
            ]
        )
        schema["sort_order"] = config.String(choices=["date", "A-Z", "a-z"])
        schema["auto_setup"] = config.Boolean()
        schema["auto_set_repeat"] = config.Deprecated()
        schema["cache_time_to_live"] = config.Integer(minimum=0)
        schema["event_support_enabled"] = config.Boolean()
        schema["double_click_interval"] = config.String()
        schema["on_pause_resume_click"] = config.String(
            choices=[
                "thumbs_up",
                "thumbs_down",
                "sleep",
                "add_artist_bookmark",
                "add_song_bookmark",
                "delete_station",
            ]
        )
        schema["on_pause_next_click"] = config.String(
            choices=[
                "thumbs_up",
                "thumbs_down",
                "sleep",
                "add_artist_bookmark",
                "add_song_bookmark",
                "delete_station",
            ]
        )
        schema["on_pause_previous_click"] = config.String(
            choices=[
                "thumbs_up",
                "thumbs_down",
                "sleep",
                "add_artist_bookmark",
                "add_song_bookmark",
                "delete_station",
            ]
        )
        schema["on_pause_resume_pause_click"] = config.String(
            choices=[
                "thumbs_up",
                "thumbs_down",
                "sleep",
                "add_artist_bookmark",
                "add_song_bookmark",
                "delete_station",
            ]
        )
        return schema

    def setup(self, registry):
        from .backend import PandoraBackend
        from .frontend import EventMonitorFrontend, PandoraFrontend

        registry.add("backend", PandoraBackend)
        registry.add("frontend", PandoraFrontend)
        registry.add("frontend", EventMonitorFrontend)
