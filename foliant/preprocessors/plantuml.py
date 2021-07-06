'''
PlantUML diagrams preprocessor for Foliant documenation authoring tool.
'''

import re

from collections import namedtuple
from hashlib import md5
from pathlib import Path
from pathlib import PosixPath
from subprocess import PIPE
from subprocess import Popen
from typing import Optional
from typing import Union

from foliant.preprocessors.utils.combined_options import CombinedOptions
from foliant.preprocessors.utils.combined_options import Options
from foliant.preprocessors.utils.preprocessor_ext import BasePreprocessorExt
from foliant.preprocessors.utils.preprocessor_ext import allow_fail
from foliant.utils import output


BUFFER_TAG = '_plantuml'
PIPE_DELIMITER = '_~_diagram_sep_~_'


OptionValue = Union[int, float, bool, str]
QueueElement = namedtuple('QueueElement', 'args sources filenames')


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

    pattern = re.compile(r'(@startuml.+?\n)\s*(@enduml)', flags=re.DOTALL)
    match = pattern.search(source)
    if match:
        return match.group(1) + match.group(2)
    else:
        return None


def generate_args(original_params: dict, diag_format: str, plantuml_path: str) -> list:
    """
    Generate a list of command line arguments needed to build this diagram. The list is sorted
    in alphabetical order except the first argument (plantuml path).

    :param original_params: cmd params as stated by user ('params' key from diagram options).
    :param diag_format: output format of the diagram without without leading dot (e.g. 'png').
    :param plantuml_path: path to plantuml executable.

    :returns: list of command line arguments ready to be fed to Popen.
    """

    components = [plantuml_path]

    params = {k: v for k, v in original_params.items() if not k.lower().startswith('t')}
    params[f't{diag_format}'] = True

    for option_name, option_value in sorted(params.items()):
        if option_value is True:
            components.append(f'-{option_name}')
        elif option_value is not False:
            components.extend((f'-{option_name}', f'{option_value}'))

    return components


def generate_buffer_tag(diagram_path: PosixPath, options: Options) -> str:
    '''
    Generate a buffer tag which should be put in place of a PlantUML diagram in Markdown source.

    After processing the queue these tags should be replaced by Markdown image tags or inline
    diagram code.

    :param diagram_path: path to the generated diagram image file (if not in cache, it doesn't exist
                         at this stage).
    :param options: diagram options.

    :returns string with a generated buffer tag:
    '''
    allow_inline = ('.svg',)

    inline = diagram_path.suffix in allow_inline and options['as_image'] is False
    caption = options.get('caption', '')

    result = f'<{BUFFER_TAG} file="{diagram_path}" inline="{inline}" caption="{caption}"></{BUFFER_TAG}>'

    return result


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
        self._queue = {}

        self.logger.debug(f'Preprocessor inited: {self.__dict__}')

    def process_plantuml(self, content: str) -> str:
        '''
        Find diagram definitions and replace them buffer tags. These tags will be processed
        on the second pass.

        The definitions are saved into the queue which will be executed after the first pass
        is finished.

        :param content: chapter's markdown content

        :returns: Markdown content with diagrams definitions replaced with buffer tags.
        '''

        raw_pattern = re.compile(
            r'(?:^|\n)(?P<spaces>[ \t]*)(?P<body>@startuml.+?@enduml)',
            flags=re.DOTALL
        )

        def _sub_tags(diagram) -> str:
            '''Sub function for <plantuml> tags.'''
            options = CombinedOptions(
                {
                    'config': self.options,
                    'tag': self.get_options(diagram.group('options'))
                },
                priority='tag'
            )
            return self._process_diagram(options, diagram.group('body'))

        def _sub_raw(diagram) -> str:
            '''
            Sub function for raw diagrams replacement (without ``<plantuml>``
            tags). Handles alternation and returns spaces which were used to
            filter out inline mentions of ``@startuml``.
            '''

            spaces = diagram.group('spaces')
            body = diagram.group('body')
            return spaces + self._process_diagram(Options(self.options), body)

        processed = self.pattern.sub(_sub_tags, content)

        if self.options['parse_raw']:
            processed = raw_pattern.sub(_sub_raw, processed)

        return processed

    @allow_fail()
    def _process_diagram(self, options: Options, body: str) -> str:
        '''
        Add PlantUML diagram to execution queue if it was not found in cache. Save the diagram
        source into .diag file for debug.

        Finally, replace diagram definition with a buffer tag. After the queue is processed
        this tag will be replaced by Markdown image or inline diagram code.

        :param options: Options extracted from the diagram definition
        :param body: PlantUML diagram body

        :returns: Buffer tag to be processed on the second pass.
        '''

        diagram_source = parse_diagram_source(body)
        if not diagram_source:
            self._warning('Cannot parse diagram body. Have you forgotten @startuml or @enduml?')
            return ''

        self._cache_path.mkdir(parents=True, exist_ok=True)

        self.logger.debug(f'Processing PlantUML diagram, options: {options}, body: {body}')

        diag_format = get_diagram_format(options)
        original_params = options.get('params', {})
        if not isinstance(original_params, dict):
            raise ValueError(f'"params" should be dict, got {type(original_params).__name__}')
        cmd_args = generate_args(original_params, diag_format, options['plantuml_path'])

        body_hash = md5(f'{cmd_args}{body}'.encode())
        diag_output_path = self._cache_path / f'{body_hash.hexdigest()}.{diag_format}'

        if diag_output_path.exists():
            self.logger.debug('Diagram image found in cache')
        else:
            self.logger.debug('Adding diagram to queue')
            self._add_to_queue(cmd_args, diagram_source, diag_output_path)
            self.logger.debug('Diagram added to queue')

        # saving diagram source into file for debug
        diag_src_path = diag_output_path.with_suffix('.diag')
        with open(diag_src_path, 'w', encoding='utf8') as diag_src_file:
            diag_src_file.write(body)

        buffer_tag = generate_buffer_tag(diag_output_path, options)
        self.logger.debug(f'Generated buffer tag: {buffer_tag}')
        return buffer_tag

    def _add_to_queue(self, cmd_args: list, diagram_src: str, output_filename: str):
        """
        Add diagram to execution queue. The queue is groupped by cmd_args so diagrams
        with the same settings will be processed by a single PlantUML instance.

        :param cmd_args: list of command line arguments for the diagram.
        :param diagram_src: source code of the diagram.
        :param output_filename: destination path of the generated diagram.
        """

        key = ' '.join(cmd_args)

        _, sources, filenames = self._queue.setdefault(key, QueueElement(cmd_args, [], []))
        sources.append(diagram_src)
        filenames.append(output_filename)

    def execute_queue(self):
        """
        Generate all diagrams which were scheduled in the queue. The queue is groupped by
        cmd_args so diagrams with the same settings will be processed by a single PlantUML
        instance.
        """

        self.logger.debug(f'Generating diagrams. Number of queues: {len(self._queue)}')
        pipe_args = ['-pipe', '-pipeNoStderr', '-pipedelimitor', PIPE_DELIMITER]

        for args, sources, filenames in self._queue.values():
            self.logger.debug(f'Queue started. Number of diagrams: {len(sources)}')
            full_args = [*args, *pipe_args]
            self.logger.debug(f'Generating diagrams from queue, command: {" ".join(full_args)}')
            p = Popen(full_args, stdout=PIPE, stdin=PIPE, stderr=PIPE)

            input_str = '\n\n'.join(sources).encode()
            r = p.communicate(input_str)

            results = r[0].split(PIPE_DELIMITER.encode())[:-1]
            self.logger.debug(f'Queue processed. Number of results: {len(results)}.')

            for bytes_, dest in zip(results, filenames):
                if bytes_.strip().startswith(b'ERROR'):
                    message = f'{"*"*10}\nFailed to generate diagram {dest}:\n{bytes_.decode()}'
                    self.logger.warning(message)
                    output(message, self.quiet)
                else:
                    with open(dest, 'wb') as f:
                        f.write(bytes_.strip())

    def replace_buffers(self, match):
        """
        re.sub function

        Replaces buffer tags, which were left in places of diagrams on the first pass, by
        Markdown image tags or by inline diagram code.
        """

        self.logger.debug(f'processing buffer tag: {match.group(0)}')
        options = self.get_options(match.group('options'))
        diag_path = Path(options['file'])
        if not diag_path.exists():
            self.logger.warning(f'Diagram {diag_path} was not generated, skipping')
            return ''

        if options['inline']:
            with open(diag_path) as f:
                diagram_source = f.read()
            return f'<div>{diagram_source}</div>'

            # # remove plantuml md5 comment because it contains diagram definition
            # # (proved not necessary after 1.0.9)
            # md5_pattern = re.compile(r'<!--MD5.+?-->', re.DOTALL)
            # return md5_pattern.sub('', result)
        else:
            caption = options.get('caption', '')
            image_path = diag_path.absolute().as_posix()
            return f'![{caption}]({image_path})'

    def apply(self):
        self._process_all_files(func=self.process_plantuml)
        self.execute_queue()

        self._process_tags_for_all_files(func=self.replace_buffers)

        self.logger.info('Preprocessor applied')
