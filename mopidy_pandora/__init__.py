from __future__ import unicode_literals

import logging
import os

from mopidy import config, ext
from mopidy.config import Deprecated

from pandora import BaseAPIClient


__version__ = '0.1.8'

logger = logging.getLogger(__name__)


class Extension(ext.Extension):

    dist_name = 'Mopidy-Pandora'
    ext_name = 'pandora'
    version = __version__

    def get_default_config(self):
        conf_file = os.path.join(os.path.dirname(__file__), 'ext.conf')
        return config.read(conf_file)

    def get_config_schema(self):
        schema = super(Extension, self).get_config_schema()
        schema['api_host'] = config.String(optional=True)
        schema['partner_encryption_key'] = config.String()
        schema['partner_decryption_key'] = config.String()
        schema['partner_username'] = config.String()
        schema['partner_password'] = config.String()
        schema['partner_device'] = config.String()
        schema['username'] = config.String()
        schema['password'] = config.Secret()
        schema['preferred_audio_quality'] = config.String(optional=True, choices=[BaseAPIClient.LOW_AUDIO_QUALITY,
                                                                                  BaseAPIClient.MED_AUDIO_QUALITY,
                                                                                  BaseAPIClient.HIGH_AUDIO_QUALITY])
        schema['sort_order'] = config.String(optional=True, choices=['date', 'A-Z', 'a-z'])
        schema['auto_setup'] = config.Boolean()
        schema['auto_set_repeat'] = Deprecated()
        schema['event_support_enabled'] = config.Boolean()
        schema['double_click_interval'] = config.String()
        schema['on_pause_resume_click'] = config.String(choices=['thumbs_up', 'thumbs_down', 'sleep'])
        schema['on_pause_next_click'] = config.String(choices=['thumbs_up', 'thumbs_down', 'sleep'])
        schema['on_pause_previous_click'] = config.String(choices=['thumbs_up', 'thumbs_down', 'sleep'])
        return schema

    def setup(self, registry):
        from .backend import PandoraBackend
        registry.add('backend', PandoraBackend)
