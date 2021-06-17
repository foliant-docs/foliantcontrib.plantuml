'''
PlantUML diagrams preprocessor for Foliant documenation authoring tool.
'''

import re
import os
from pathlib import Path, PosixPath
from hashlib import md5
from subprocess import Popen, run, PIPE, STDOUT, CalledProcessError
from typing import Dict, Union, List, Optional
from collections import namedtuple

# from foliant.preprocessors.base import BasePreprocessor
from foliant.utils import output
from foliant.preprocessors.utils.combined_options import CombinedOptions, Options
from foliant.preprocessors.utils.preprocessor_ext import BasePreprocessorExt


OptionValue = Union[int, float, bool, str]

BUFFER_TAG = '_plantuml'
PIPE_DELIMITER = '_~_diagram_sep_~_'


class PlantUMLPipeQueue:
    def __init__(self, logger, quiet):
        self.logger = logger
        self.quiet = quiet
        self.queue = {}
        self.QueueElement = namedtuple('QueueElement', 'args sources filenames')

    def add_to_queue(self, cmd_args: list, diagram_src: str, output_filename: str):
        self.logger.debug('Adding diagram to queue')

        key = ' '.join(cmd_args)

        _, sources, filenames = self.queue.setdefault(key, self.QueueElement(cmd_args, [], []))
        sources.append(diagram_src)
        filenames.append(output_filename)

        self.logger.debug('Diagram added to queue')

    def execute(self):
        self.logger.debug(f'Generating diagrams. Number of queues: {len(self.queue)}')
        pipe_args = ['-pipe', '-pipeNoStderr', '-pipedelimitor', PIPE_DELIMITER]

        for args, sources, filenames in self.queue.values():
            self.logger.debug(f'Queue started. Number of diagrams: {len(sources)}')
            full_args = [*args, *pipe_args]
            p = Popen(full_args, stdout=PIPE, stdin=PIPE, stderr=PIPE)

            input_str = '\n\n'.join(sources).encode()
            r = p.communicate(input_str)

            results = r[0].split(PIPE_DELIMITER.encode())
            self.logger.debug(f'Queue processed. Number of results: {len(results)}')

            for bytes_, dest in zip(results, filenames):
                if bytes_.strip().startswith(b'ERROR'):
                    message = f'Failed to generate diagram {dest}:\n{bytes_.decode()}'
                    self.logger.warning(message)
                    output(message, self.quiet)
                else:
                    with open(dest, 'wb') as f:
                        f.write(bytes_.strip())


def get_diagram_format(options: CombinedOptions) -> str:
    '''
    Parse options and get the final diagram format. Format stated in params
    (e.g. tsvg) has higher priority.

    :param options: the options object to be parsed

    :returns: the diagram format string
    '''
    result = None
    for key in options.get('params', {}):
        if key.lower().startswith('t'):
            result = key[1:]
    return result or options['format']


def parse_diagram_source(source: str) -> Optional[str]:
    """
    Parse source string and get a diagram out of it.
    All text before the first @startuml and after the first @enduml is cut out.
    All spaces before @startuml and @enduml are also removed.

    :param source: diagram source string as stated by user.

    :returns: parsed diagram source or None if parsing failed.
    """

    pattern = re.compile(r'(@startuml.+\n)\s*(@enduml)', flags=re.DOTALL)
    match = pattern.search(source)
    if match:
        return match.group(1) + match.group(2)
    else:
        return None


def generate_components(original_params: dict, diag_format: str, plantuml_path: str):
    components = [plantuml_path]

    params = {k: v for k, v in original_params.items() if not k.lower().startswith('t')}
    params[f't{diag_format}'] = True

    for option_name, option_value in sorted(params.items()):
        if option_value is True:
            components.append(f'-{option_name}')
        else:
            components.extend((f'-{option_name}', f'{option_value}'))

    return components


class Preprocessor(BasePreprocessorExt):
    defaults = {
        'cache_dir': Path('.diagramscache'),
        'plantuml_path': 'plantuml',
        'parse_raw': False,
        'format': 'png',
        'as_image': True
    }
    tags = ('plantuml', BUFFER_TAG)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._cache_path = self.project_path / self.options['cache_dir'] / 'plantuml'

        self.logger = self.logger.getChild('plantuml')
        self._queue = PlantUMLPipeQueue(self.logger, self.quiet)

        self.logger.debug(f'Preprocessor inited: {self.__dict__}')

    def _generate_buffer_tag(self, diagram_path: PosixPath, options: CombinedOptions, diagram_format: str):
        '''Get either image ref or a marker for raw image code post insertion depending on as_image option'''
        allow_inline = ('svg',)

        inline = diagram_format in allow_inline and options['as_image'] is False
        caption = options.get('caption', '')

        result = f'<{BUFFER_TAG} file="{diagram_path}" inline="{inline}" caption="{caption}"></{BUFFER_TAG}>'
        self.logger.debug(f'Generated buffer tag: {result}')

        return result

        # if diagram_format in allow_inline and options['as_image'] is False:
        #     self._need_post_process_inline = True
        #     return f'<{INLINE_TAG} file="{diagram_path}"></{INLINE_TAG}>'
        # else:
        #     return f'![{options.get("caption", "")}]({diagram_path.absolute().as_posix()})'

    def _process_plantuml(self, options: Options, body: str) -> str:
        '''Save PlantUML diagram body to .diag file, generate an image from it,
        and return the image ref.

        If the image for this diagram has already been generated, the existing version
        is used.

        :param options: Options extracted from the diagram definition
        :param body: PlantUML diagram body

        :returns: Image ref
        '''
        diagram_source = parse_diagram_source(body)
        if not diagram_source:
            self._warning('Cannot parse diagram body. Have you forgotten @startuml or @enduml?')
            return ''

        self._cache_path.mkdir(parents=True, exist_ok=True)

        self.logger.debug(f'Processing PlantUML diagram, options: {options}, body: {body}')

        diag_format = get_diagram_format(options)
        cmd_args = generate_components(options.get('params', {}), diag_format, options['plantuml_path'])

        body_hash = md5(f'{cmd_args}{body}'.encode())
        diag_output_path = self._cache_path / f'{body_hash.hexdigest()}.{diag_format}'

        if diag_output_path.exists():
            self.logger.debug('Diagram image found in cache')
        else:
            self._queue.add_to_queue(cmd_args, diagram_source, diag_output_path)

        # saving diagram source into file for debug
        diag_src_path = diag_output_path.with_suffix('.diag')
        with open(diag_src_path, 'w', encoding='utf8') as diag_src_file:
            diag_src_file.write(body)

        return self._generate_buffer_tag(diag_output_path, options, diag_format)

    def process_plantuml(self, content: str) -> str:
        '''Find diagram definitions and replace them with image refs.

        The definitions are fed to PlantUML processor that convert them into images.

        :param content: Markdown content

        :returns: Markdown content with diagrams definitions replaced with image refs
        '''

        raw_pattern = re.compile(
            r'(?:^|\n)(?P<spaces>[ \t]*)(?P<body>@startuml.+?@enduml)',
            flags=re.DOTALL
        )

        def _sub(diagram) -> str:
            options = CombinedOptions(
                {
                    'config': self.options,
                    'tag': self.get_options(diagram.group('options'))
                },
                priority='tag'
            )
            return self._process_plantuml(
                options,
                diagram.group('body')
            )

        def _sub_raw(diagram) -> str:
            '''
            Sub function for raw diagrams replacement (without ``<plantuml>``
            tags). Handles alternation and returns spaces which were used to
            filter out inline mentions of ``@startuml``
            '''

            spaces = diagram.group('spaces')
            body = diagram.group('body')
            return spaces + self._process_plantuml(Options(self.options), body)

        # Process tags
        processed = self.pattern.sub(_sub, content)
        # Process raw diagrams
        if self.options['parse_raw']:
            processed = raw_pattern.sub(_sub_raw, processed)

        return processed

    def replace_buffers(self, match):
        self.logger.debug(f'processing buffer tag: {match.group(0)}')
        options = self.get_options(match.group('options'))
        diag_path = Path(options['file'])
        if not diag_path.exists():
            self.logger.warning(f'Diagram {diag_path} was not generated, skipping')
            return ''

        if options['inline']:
            with open(diag_path) as f:
                diagram_source = f.read()
            result = f'<div>{diagram_source}</div>'

            # remove plantuml md5 comment because it contains diagram definition
            md5_pattern = re.compile(r'<!--MD5.+?-->', re.DOTALL)
            return md5_pattern.sub('', result)
        else:
            caption = options.get('caption', '')
            image_path = diag_path.absolute().as_posix()
            return f'![{caption}]({image_path})'

    def apply(self):
        self._process_all_files(func=self.process_plantuml)
        self._queue.execute()

        self._process_tags_for_all_files(func=self.replace_buffers)

        self.logger.info('Preprocessor applied')
