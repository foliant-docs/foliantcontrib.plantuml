'''
PlantUML diagrams preprocessor for Foliant documenation authoring tool.
'''

from pathlib import Path
from hashlib import md5
from subprocess import run, PIPE, STDOUT, CalledProcessError
from typing import Dict
OptionValue = int or float or bool or str

from foliant.preprocessors.base import BasePreprocessor


class Preprocessor(BasePreprocessor):
    defaults = {
        'cache_dir': Path('.diagramscache'),
        'plantuml_path': 'plantuml',
    }
    tags = 'plantuml',

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._cache_path = self.project_path / self.options['cache_dir']

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

        for option_name, option_value in {**options, **params}.items():
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

        body_hash = md5(f'{body}'.encode())
        body_hash.update(str(self.options).encode())

        diagram_src_path = self._cache_path / 'plantuml' / f'{body_hash.hexdigest()}.diag'

        params = self.options.get('params', {})

        diagram_format = {**options, **params}.get('format', 'png')

        diagram_path = diagram_src_path.with_suffix(f'.{diagram_format}')

        img_ref = f'![{options.get("caption", "")}]({diagram_path.absolute().as_posix()})'

        if diagram_path.exists():
            return img_ref

        diagram_src_path.parent.mkdir(parents=True, exist_ok=True)

        with open(diagram_src_path, 'w', encoding='utf8') as diagram_src_file:
            diagram_src_file.write(body)

        try:
            command = self._get_command(options, diagram_src_path)
            run(command, shell=True, check=True, stdout=PIPE, stderr=STDOUT)

        except CalledProcessError as exception:
            raise RuntimeError(
                f'Processing of PlantUML diagram {diagram_src_path} failed: {exception.output.decode()}'
            )

        return img_ref

    def process_plantuml(self, content: str) -> str:
        '''Find diagram definitions and replace them with image refs.

        The definitions are fed to PlantUML processor that convert them into images.

        :param content: Markdown content

        :returns: Markdown content with diagrams definitions replaced with image refs
        '''

        def _sub(diagram) -> str:
            return self._process_plantuml(
                self.get_options(diagram.group('options')),
                diagram.group('body')
            )

        return self.pattern.sub(_sub, content)

    def apply(self):
        for markdown_file_path in self.working_dir.rglob('*.md'):
            with open(markdown_file_path, encoding='utf8') as markdown_file:
                content = markdown_file.read()
            with open(markdown_file_path, 'w', encoding='utf8') as markdown_file:
                markdown_file.write(self.process_plantuml(content))
