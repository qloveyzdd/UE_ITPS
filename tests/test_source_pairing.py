from pathlib import Path
import sys
import tempfile
import unittest

from tests.support import ROOT, create_fixture, run_cli, write_text

sys.path.insert(0, str(ROOT / 'sourcetools'))
from ue_project_tools.project_cxx_sources import list_module_cxx_sources


class SourcePairingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.fixture = create_fixture(Path(directory.name))
        self.module = self.fixture.module_rules.parent

    def add(self, relative):
        return write_text(self.module / relative, '// selected source')

    def test_unique_same_module_name_across_directories(self):
        header = self.add('Public/Tracker.h')
        source = self.add('Private/Registry/Tracker.cpp')
        result = list_module_cxx_sources(self.fixture.module_rules)
        pair = next(p for p in result['pairs'] if p['header'].endswith('/Tracker.h'))
        self.assertEqual(pair['method'], 'unique-module-basename')
        self.assertEqual(self.fixture.project.parent / pair['cpp'], source)
        self.assertEqual(self.fixture.project.parent / pair['header'], header)
        self.assertFalse(any(p.endswith('Tracker.cpp') for p in result['cpp_only']))

    def test_ambiguous_fallback_retains_every_candidate(self):
        self.add('Public/A/Tracker.h')
        self.add('Public/B/Tracker.hpp')
        self.add('Private/Registry/Tracker.cpp')
        result = list_module_cxx_sources(self.fixture.module_rules)
        self.assertFalse(any('Tracker' in p['header'] for p in result['pairs']))
        problem = next(p for p in result['validation']['problems'] if p['code'] == 'source-pair-ambiguous')
        self.assertEqual((len(problem['headers']), len(problem['cpp'])), (2, 1))

    def test_conventional_matches_and_nested_modules_remain_separate(self):
        self.add('Public/A/Tracker.h')
        self.add('Private/A/Tracker.cpp')
        self.add('Public/B/Tracker.h')
        self.add('Private/B/Tracker.cpp')
        self.add('Public/Remote.h')
        self.add('Nested/Nested.Build.cs')
        self.add('Nested/Private/Remote.cpp')
        result = list_module_cxx_sources(self.fixture.module_rules)
        self.assertEqual(len([p for p in result['pairs'] if 'Tracker' in p['header']]), 2)
        self.assertTrue(any(p.endswith('/Remote.h') for p in result['header_only']))
        self.assertFalse(any('Nested' in p for p in result['cpp_only']))
        completed, cli = run_cli('sourcetools/ue_list_module_cxx_sources.py', '--rules', self.fixture.module_rules)
        self.assertEqual(completed.returncode, 0, cli)
        self.assertEqual(cli, result)
