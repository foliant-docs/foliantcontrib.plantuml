# PlantUML Diagrams Preprocessor for Foliant

[PlantUML](http://plantuml.com/) is a tool to generate diagrams from plain text. This preprocessor finds PlantUML diagrams definitions in the source and converts them into images on the fly during project build.

## Installation

```bash
$ pip install foliantcontrib.plantuml
```

## Config

To enable the preprocessor, add `plantuml` to `preprocessors` section in the project config:

```yaml
preprocessors:
    - plantuml
```

The preprocessor has a number of options:

```yaml
preprocessors:
    - plantuml:
        cache_dir: !path .diagramscache
        plantuml_path: plantuml
        params:
            ...
        parse_raw: true
```

`cache_dir`
:   Path to the directory with the generated diagrams. It can be a path relative to the project root or a global one; you can use `~/` shortcut.

    >   **Note**
    >
    >   To save time during build, only new and modified diagrams are rendered. The generated images are cached and reused in future builds.

`plantuml_path`
:   Path to PlantUML launcher. By default, it is assumed that you have the command `plantuml` in your `PATH`, but if PlantUML uses another command to launch, or if the `plantuml` launcher is installed in a custom place, you can define it here.

`params`
:   Params passed to the image generation command:

        preprocessors:
            - plantuml:
                params:
                    config: !path plantuml.cfg

    To see the full list of params, run the command that launches PlantUML, with `-h` command line option.

`parse_raw`
:   If this flag is `true`, the preprocessor will also process all PlantUML diagrams which are not wrapped in `<<plantuml>...</plantuml>` tags. Default value is `false`.

## Usage

To insert a diagram definition in your Markdown source, enclose it between `<<plantuml>...</plantuml>` tags (indentation inside tags is optional):

```markdown
Here’s a diagram:

<<plantuml>
    @startuml
        ...
    @enduml
</plantuml>
```

To set a caption, use `caption` option:

```markdown
Diagram with a caption:

<<plantuml caption="Sample diagram from the official site">
    @startuml
        ...
    @enduml
</plantuml>
```

You can override `params` values from the preprocessor config for each diagram. Also you can use `format` alias for `-t*` params:

```markdown
By default, diagrams are in PNG. But this diagram is in EPS:

<<plantuml caption="Vector diagram" format="eps">
    @startuml
        ...
    @enduml
</plantuml>
```

Sometimes it can be necessary to process auto-generated documents that contain multiple PlantUML diagrams definitions without using Foliant-specific tags syntax. Use the `parse_raw` option in these cases.
