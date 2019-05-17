'''
PlantUML diagrams preprocessor for Foliant documenation authoring tool.
'''

import re
from pathlib import Path
from hashlib import md5
from subprocess import run, PIPE, STDOUT, CalledProcessError
from typing import Dict
OptionValue = int or float or bool or str

from foliant.preprocessors.base import BasePreprocessor
from foliant.utils import output


class Preprocessor(BasePreprocessor):
    defaults = {
        'cache_dir': Path('.diagramscache'),
        'plantuml_path': 'plantuml',
        'parse_raw': False,
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
            diagram_src_path: Path
        ) -> str:
        '''Generate the image generation command. Options from the config definition are passed
        as command options (``cache_dir`` and ``plantuml_path`` options are omitted).

        :param options: Options extracted from the diagram definition
        :param diagram_src_path: Path to the diagram source file

        :returns: Complete image generation command
        '''

        components = [self.options['plantuml_path']]

        params = self.options.get('params', {})

        for option_name, option_value in {**params, **options}.items():
            if option_name == 'caption':
                continue

            elif option_value is True:
                components.append(f'-{option_name}')

            elif option_name == 'format':
                components.append(f'-t{option_value}')

            else:
                components.append(f'-{option_name} {option_value}')

        components.append(str(diagram_src_path))

        return ' '.join(components)

    def _process_plantuml(self, options: Dict[str, OptionValue], body: str) -> str:
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

        params = self.options.get('params', {})

        diagram_format = {**params, **options}.get('format', 'png')

        diagram_path = diagram_src_path.with_suffix(f'.{diagram_format}')

        self.logger.debug(f'Diagram image path: {diagram_path}')

        img_ref = f'![{options.get("caption", "")}]({diagram_path.absolute().as_posix()})'

        if diagram_path.exists():
            self.logger.debug('Diagram image found in cache')

            return img_ref

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
                    f'Processing of PlantUML diagram {diagram_src_path} failed: ' +
                    f'{exception.output.decode()}'
                )

                output(error_message, self.quiet)

                self.logger.error(error_message)

            else:
                raise RuntimeError(f'Failed: {exception.output.decode()}')

        return img_ref

    def process_plantuml(self, content: str) -> str:
        '''Find diagram definitions and replace them with image refs.

        The definitions are fed to PlantUML processor that convert them into images.

        :param content: Markdown content

        :returns: Markdown content with diagrams definitions replaced with image refs
        '''

        raw_pattern = re.compile(
            r'^(\s*)(@startuml.+?@enduml)' +
            r'|(?<=\n)(\s*)(@startuml.+?@enduml)',
            flags=re.DOTALL
        )

        def _sub(diagram) -> str:
            return self._process_plantuml(
                self.get_options(diagram.group('options')),
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
            return spaces + self._process_plantuml({}, body)

        # Process tags
        processed = self.pattern.sub(_sub, content)

        # Process raw diagrams
        if self.options['parse_raw']:
            processed = raw_pattern.sub(_sub_raw, processed)

        return processed

    def apply(self):
        self.logger.info('Applying preprocessor')

        for markdown_file_path in self.working_dir.rglob('*.md'):
            with open(markdown_file_path, encoding='utf8') as markdown_file:
                content = markdown_file.read()

            processed_content = self.process_plantuml(content)

            if processed_content:
                with open(markdown_file_path, 'w', encoding='utf8') as markdown_file:
                    markdown_file.write(processed_content)

        self.logger.info('Preprocessor applied')
