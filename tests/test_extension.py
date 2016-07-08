from __future__ import absolute_import, division, print_function, unicode_literals

import unittest

import mock

from mopidy_pandora import Extension

from mopidy_pandora import backend as backend_lib
from mopidy_pandora import frontend as frontend_lib


class ExtensionTests(unittest.TestCase):

    def test_get_default_config(self):
        ext = Extension()

        config = ext.get_default_config()

        assert '[pandora]'in config
        assert 'enabled = true'in config
        assert 'api_host = tuner.pandora.com/services/json/'in config
        assert 'partner_encryption_key ='in config
        assert 'partner_decryption_key ='in config
        assert 'partner_username = android'in config
        assert 'partner_password ='in config
        assert 'partner_device = android-generic'in config
        assert 'username ='in config
        assert 'password ='in config
        assert 'preferred_audio_quality = highQuality'in config
        assert 'sort_order = a-z'in config
        assert 'auto_setup = true'in config
        assert 'cache_time_to_live = 86400'in config
        assert 'event_support_enabled = false'in config
        assert 'double_click_interval = 2.50'in config
        assert 'on_pause_resume_click = thumbs_up'in config
        assert 'on_pause_next_click = thumbs_down'in config
        assert 'on_pause_previous_click = sleep'in config
        assert 'on_pause_resume_pause_click = delete_station'in config

    def test_get_config_schema(self):
        ext = Extension()

        schema = ext.get_config_schema()

        assert 'enabled'in schema
        assert 'api_host'in schema
        assert 'partner_encryption_key'in schema
        assert 'partner_decryption_key'in schema
        assert 'partner_username'in schema
        assert 'partner_password'in schema
        assert 'partner_device'in schema
        assert 'username'in schema
        assert 'password'in schema
        assert 'preferred_audio_quality'in schema
        assert 'sort_order'in schema
        assert 'auto_setup'in schema
        assert 'cache_time_to_live'in schema
        assert 'event_support_enabled'in schema
        assert 'double_click_interval'in schema
        assert 'on_pause_resume_click'in schema
        assert 'on_pause_next_click'in schema
        assert 'on_pause_previous_click'in schema
        assert 'on_pause_resume_pause_click'in schema

    def test_setup(self):
        registry = mock.Mock()

        ext = Extension()
        ext.setup(registry)
        calls = [mock.call('frontend', frontend_lib.PandoraFrontend),
                 mock.call('backend',  backend_lib.PandoraBackend)]
        registry.add.assert_has_calls(calls, any_order=True)
