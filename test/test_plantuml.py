import logging
import shutil
import os
import re
import io
import sys

from foliant_test.preprocessor import PreprocessorTestFramework
from foliant_test.preprocessor import unpack_file_dict
from unittest import TestCase


def rel_name(path: str):
    return os.path.join(os.path.dirname(__file__), path)


def count_output_mentions(source, mention) -> int:
    return source.getvalue().count(mention)


logging.disable(logging.CRITICAL)


class TestPlantuml(TestCase):
    def setUp(self):
        self.ptf = PreprocessorTestFramework('plantuml')
        self.ptf.quiet = False
        self.ptf.capturedOutput = io.StringIO()
        self.original_stdout = sys.stdout
        sys.stdout = self.ptf.capturedOutput

    def tearDown(self):
        shutil.rmtree('.diagramscache', ignore_errors=True)

    def test_correct_tags(self):
        self.ptf.test_preprocessor(
            input_mapping=unpack_file_dict(
                {'index.md': rel_name('data/two_good_tags.md')}
            )
        )

        result = self.ptf.results['index.md']

        images = re.findall(r'!\[\]\(.+\)', result)
        self.assertEqual(len(images), 2)

    def test_correct_raw(self):
        self.ptf.options = {'parse_raw': True}
        self.ptf.test_preprocessor(
            input_mapping=unpack_file_dict(
                {'index.md': rel_name('data/two_good_raw.md')}
            )
        )

        result = self.ptf.results['index.md']

        images = re.findall(r'!\[\]\(.+\)', result)
        self.assertEqual(len(images), 2)

    def test_good_and_faulty(self):
        self.ptf.options = {'parse_raw': True}
        self.ptf.test_preprocessor(
            input_mapping=unpack_file_dict(
                {'index.md': rel_name('data/two_good_two_bad.md')}
            )
        )

        result = self.ptf.results['index.md']

        images = re.findall(r'!\[\]\(.+\)', result)
        self.assertEqual(len(images), 2)

        self.assertEqual(count_output_mentions(self.ptf.capturedOutput, 'ERROR'), 2)

    def test_good_and_faulty_uml_tags(self):
        self.ptf.options = {'parse_raw': True}
        self.ptf.test_preprocessor(
            input_mapping=unpack_file_dict(
                {'index.md': rel_name('data/two_good_two_bad2.md')}
            )
        )

        result = self.ptf.results['index.md']

        images = re.findall(r'!\[\]\(.+\)', result)
        self.assertEqual(len(images), 2)

        self.assertEqual(count_output_mentions(self.ptf.capturedOutput, 'WARNING'), 2)

    def test_inline(self):
        self.ptf.options = {'format': 'svg', 'as_image': False}
        self.ptf.test_preprocessor(
            input_mapping=unpack_file_dict(
                {'index.md': rel_name('data/two_good_tags.md')}
            )
        )

        result = self.ptf.results['index.md']

        images = re.findall(r'<svg .+?</svg>', result, flags=re.DOTALL)
        self.assertEqual(len(images), 2)
