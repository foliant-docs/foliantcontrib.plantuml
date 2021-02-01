# 1.0.8

-   Config options now can be overriden in tag options.
-   Add `as_image` option, which allows (when `false`) to insert svg-code instead of image into the document.

# 1.0.6

-   Attributes of `<plantuml>` tag have higher priority than config file options.

# 1.0.5

-   Do not rewrite source Markdown file if an error occurs.
-   Use output() method and Foliant 1.0.8.

# 1.0.4

-   Additionally сheck if diagram image is not saved.

# 1.0.3

-   Add `parse_raw` option.
-   Do not fail the preprocessor if some diagrams contain errors. Write error messages into the log.

# 1.0.2

-   Fix logging in `__init__`.

# 1.0.1

-   Add logging.
