from unittest import TestCase
from pathlib import Path

from foliant.preprocessors.utils.combined_options import Options
from foliant.preprocessors.plantuml import get_diagram_format
from foliant.preprocessors.plantuml import parse_diagram_source
from foliant.preprocessors.plantuml import generate_args
from foliant.preprocessors.plantuml import generate_buffer_tag
from foliant.preprocessors.plantuml import BUFFER_TAG


class TestGetDiagramFormat(TestCase):
    def test_format_in_params(self):
        options_dict = {
            'params': {
                'charset': 'utf8',
                'tsvg': True,
                'failfast': False
            }
        }
        options = Options(options_dict)
        diag_format = get_diagram_format(options)
        self.assertEqual(diag_format, 'svg')

    def test_format_in_params_uppercase(self):
        options_dict = {
            'params': {
                'charset': 'utf8',
                'Tsvg': True,
                'failfast': False
            }
        }
        options = Options(options_dict)
        diag_format = get_diagram_format(options)
        self.assertEqual(diag_format, 'svg')

    def test_format_in_options(self):
        options_dict = {
            'format': 'png',
            'params': {
                'charset': 'utf8',
                'failfast': False
            }
        }
        options = Options(options_dict)
        diag_format = get_diagram_format(options)
        self.assertEqual(diag_format, 'png')

    def test_format_in_params_has_priority(self):
        options_dict = {
            'format': 'png',
            'params': {
                'tsvg': True,
                'charset': 'utf8',
                'failfast': False
            }
        }
        options = Options(options_dict)
        diag_format = get_diagram_format(options)
        self.assertEqual(diag_format, 'svg')


class TestParseDiagramSource(TestCase):
    def test_diagram_with_empty_lines(self):
        source = '@startuml\n  a -> b\n\n  c -> d\n@enduml'
        parsed = parse_diagram_source(source)

        self.assertEqual(source, parsed)

    def test_indented(self):
        source = '    @startuml\n      a -> b\n\t@enduml\n    '
        expected = '@startuml\n      a -> b\n@enduml'
        parsed = parse_diagram_source(source)

        self.assertEqual(parsed, expected)

    def test_cluttered(self):
        source = 'how did it get here?\n\n```\n\n@startuml\na -> b\n@enduml\n```\n&*^*Y'
        expected = '@startuml\na -> b\n@enduml'
        parsed = parse_diagram_source(source)

        self.assertEqual(parsed, expected)

    def test_if_several_diagrams_only_first_is_taken(self):
        source = '\n@startuml\na -> b\n@enduml\n\n@startuml\nc -> d\n@enduml\n'
        expected = '@startuml\na -> b\n@enduml'
        parsed = parse_diagram_source(source)

        self.assertEqual(parsed, expected)

    def test_diagram_without_uml_tags_is_rejected(self):
        source = 'a -> b\n\nc -> d'

        parsed = parse_diagram_source(source)
        self.assertIsNone(parsed)

    def diagram_without_start_or_end_uml_is_rejected(self):
        source = '\n@startuml\na -> b\n@enuml\n'

        parsed = parse_diagram_source(source)
        self.assertIsNone(parsed)


class TestGenerateArgs(TestCase):
    def test_args_are_sorted(self):
        params = {
            'charset': 'utf8',
            'tsvg': True,
            'enablestats': True,
        }
        plantuml = 'plantuml'
        expected = [plantuml, '-charset', 'utf8', '-enablestats', '-tsvg']

        args = generate_args(params, 'svg', plantuml)

        self.assertEqual(args, expected)

    def test_false_params_are_omitted(self):
        params = {
            'charset': 'utf8',
            'tsvg': True,
            'enablestats': True,
            'failfast': False
        }
        plantuml = 'plantuml'
        expected = [plantuml, '-charset', 'utf8', '-enablestats', '-tsvg']

        args = generate_args(params, 'svg', plantuml)

        self.assertEqual(args, expected)

    def test_format_is_taken_from_function_arg(self):
        params = {
            'charset': 'utf8',
            'tsvg': True,
            'enablestats': True,
            'failfast': False
        }
        plantuml = 'plantuml'
        expected = [plantuml, '-charset', 'utf8', '-enablestats', '-tpng']

        args = generate_args(params, 'png', plantuml)

        self.assertEqual(args, expected)


class TestGenerateBufferTag(TestCase):
    def test_not_inline_no_caption(self):
        options = Options({'as_image': False})
        diag_path = Path('/some/path/image.png')

        expected = f'<{BUFFER_TAG} file="/some/path/image.png" inline="False" caption=""></{BUFFER_TAG}>'

        tag = generate_buffer_tag(diag_path, options)

        self.assertEqual(tag, expected)

    def test_not_inline_with_caption(self):
        options = Options({'as_image': True, 'caption': 'Diagram caption'})
        diag_path = Path('/some/path/image.png')

        expected = f'<{BUFFER_TAG} file="/some/path/image.png" inline="False" caption="Diagram caption"></{BUFFER_TAG}>'

        tag = generate_buffer_tag(diag_path, options)

        self.assertEqual(tag, expected)

    def test_inline_no_caption(self):
        options = Options({'as_image': False})
        diag_path = Path('/some/path/image.svg')

        expected = f'<{BUFFER_TAG} file="/some/path/image.svg" inline="True" caption=""></{BUFFER_TAG}>'

        tag = generate_buffer_tag(diag_path, options)

        self.assertEqual(tag, expected)
