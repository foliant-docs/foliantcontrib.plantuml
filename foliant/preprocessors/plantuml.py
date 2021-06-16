'''
PlantUML diagrams preprocessor for Foliant documenation authoring tool.
'''

import re
from pathlib import Path, PosixPath
from hashlib import md5
from subprocess import run, PIPE, STDOUT, CalledProcessError
from typing import Dict, Optional

from foliant.preprocessors.base import BasePreprocessor
from foliant.utils import output
from foliant.preprocessors.utils.combined_options import CombinedOptions
from foliant.preprocessors.utils.preprocessor_ext import BasePreprocessorExt


OptionValue = Optional(int, float, bool, str)


class Preprocessor(BasePreprocessorExt):
    defaults = {
        'cache_dir': Path('.diagramscache'),
        'plantuml_path': 'plantuml',
        'parse_raw': False,
        'format': 'png',
        'as_image': True
    }
    tags = 'plantuml',

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._cache_path = self.project_path / self.options['cache_dir']

        self.logger = self.logger.getChild('plantuml')

        self.logger.debug(f'Preprocessor inited: {self.__dict__}')

    def _get_command(
            self,
            options: Dict[str, OptionValue],
            diagram_src_path: PosixPath
        ) -> str:
        '''Generate the image generation command. Options from the config definition are passed
        as command options (``cache_dir`` and ``plantuml_path`` options are omitted).

        :param options: Options extracted from the diagram definition
        :param diagram_src_path: Path to the diagram source file

        :returns: Complete image generation command
        '''

        components = [options['plantuml_path']]

        params = dict(options.get('params', {}))

        # if format is not set in parameters, set it from `format` param
        if 't' not in (k[0] for k in params.keys()):
            params[f't{options["format"]}'] = True

        for option_name, option_value in params.items():
            # if option_name == 'caption':
            #     continue

            if option_value is True:
                components.append(f'-{option_name}')

            # elif option_name == 'format':
            #     components.append(f'-t{option_value}')

            else:
                components.append(f'-{option_name} {option_value}')

        components.append(str(diagram_src_path))

        return ' '.join(components)

    def _get_result(self, diagram_path: PosixPath, options: CombinedOptions):
        '''Get either image ref or raw image code depending on as_image option'''
        diagram_format = self._get_diagram_format(options)
        if diagram_format != 'svg' or options['as_image']:
            result = f'![{options.get("caption", "")}]({diagram_path.absolute().as_posix()})'
        else:
            with open(diagram_path, 'r') as f:
                result = f'<div>{f.read()}</div>'
                # return plantuml md5 comment because it contains diagram definition
                md5_pattern = re.compile(r'<!--MD5.+?-->', re.DOTALL)
                result = md5_pattern.sub('', result)
        return result

    def _get_diagram_format(self, options: CombinedOptions) -> str:
        '''
        Parse options and get the final diagram format. Format stated in params
        (e.g. tsvg) has higher priority.

        :param options: the options object to be parsed

        :returns: the diagram format string
        '''
        result = None
        for key in options.get('params', {}):
            if key.startswith('t'):
                result = key[1:]
        return result or options['format']

    def _process_plantuml(self, options: CombinedOptions, body: str) -> str:
        '''Save PlantUML diagram body to .diag file, generate an image from it,
        and return the image ref.

        If the image for this diagram has already been generated, the existing version
        is used.

        :param options: Options extracted from the diagram definition
        :param body: PlantUML diagram body

        :returns: Image ref
        '''
        self.logger.debug(f'Processing PlantUML diagram, options: {options}, body: {body}')

        body_hash = md5(f'{body}'.encode())
        body_hash.update(str(self.options).encode())

        diagram_src_path = self._cache_path / 'plantuml' / f'{body_hash.hexdigest()}.diag'

        self.logger.debug(f'Diagram definition file path: {diagram_src_path}')

        # params = self.options.get('params', {})

        diagram_format = self._get_diagram_format(options)

        diagram_path = diagram_src_path.with_suffix(f'.{diagram_format}')

        self.logger.debug(f'Diagram image path: {diagram_path}')

        if diagram_path.exists():
            self.logger.debug('Diagram image found in cache')

            return self._get_result(diagram_path, options)

        diagram_src_path.parent.mkdir(parents=True, exist_ok=True)

        with open(diagram_src_path, 'w', encoding='utf8') as diagram_src_file:
            diagram_src_file.write(body)

            self.logger.debug(f'Diagram definition written into the file')

        try:
            command = self._get_command(options, diagram_src_path)

            self.logger.debug(f'Running the command: {command}')

            run(command, shell=True, check=True, stdout=PIPE, stderr=STDOUT)

            if diagram_path.exists():
                self.logger.debug(f'Diagram image saved')

            else:
                error_message = f'Processing of PlantUML diagram {diagram_src_path} failed: diagram image not saved'

                output(error_message, self.quiet)

                self.logger.error(error_message)

        except CalledProcessError as exception:
            self.logger.error(str(exception))

            if diagram_path.exists():
                error_diagram_path = diagram_path.parent / (diagram_path.stem + '_error' + diagram_path.suffix)
                diagram_path.rename(error_diagram_path)

                error_message = (
                    f'Processing of PlantUML diagram {diagram_src_path} failed: '
                    f'{exception.output.decode()}'
                )

                output(error_message, self.quiet)

                self.logger.error(error_message)

            else:
                raise RuntimeError(f'Failed: {exception.output.decode()}')

        return self._get_result(diagram_path, options)

    def process_plantuml(self, content: str) -> str:
        '''Find diagram definitions and replace them with image refs.

        The definitions are fed to PlantUML processor that convert them into images.

        :param content: Markdown content

        :returns: Markdown content with diagrams definitions replaced with image refs
        '''

        raw_pattern = re.compile(
            r'^(\s*)(@startuml.+?@enduml)'
            r'|(?<=\n)(\s*)(@startuml.+?@enduml)',
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

            diagram_groups = diagram.groups()
            spaces = diagram_groups[0] or diagram_groups[2]
            body = diagram_groups[1] or diagram_groups[3]
            return spaces + self._process_plantuml(self.options, body)

        # Process tags
        processed = self.pattern.sub(_sub, content)
        # Process raw diagrams
        if self.options['parse_raw']:
            processed = raw_pattern.sub(_sub_raw, processed)

        return processed

    def apply(self):
        self._process_all_files(func=self.process_plantuml, buffer=False)

        self.logger.info('Preprocessor applied')
