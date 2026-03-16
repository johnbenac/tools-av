import unittest

from av_editor.cli import normalize_argv


class TestCLIArgNormalization(unittest.TestCase):
    def test_passthrough_when_subcommand_present(self):
        self.assertEqual(
            normalize_argv(['render', 'cfg.json', '--force']),
            ['render', 'cfg.json', '--force'],
        )

    def test_legacy_shorthand_with_config_first(self):
        self.assertEqual(
            normalize_argv(['cfg.json', '--force']),
            ['render', 'cfg.json', '--force'],
        )

    def test_legacy_shorthand_with_flag_first(self):
        self.assertEqual(
            normalize_argv(['-v', '--force', 'cfg.json']),
            ['render', '-v', '--force', 'cfg.json'],
        )

    def test_top_level_help_passthrough(self):
        self.assertEqual(normalize_argv(['--help']), ['--help'])

    def test_top_level_version_passthrough(self):
        self.assertEqual(normalize_argv(['--version']), ['--version'])


if __name__ == '__main__':
    unittest.main()
