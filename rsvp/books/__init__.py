"""Loading book files into plain text.

This sub-package isolates *parsing* from the rest of the app. The core engine
and the UI only ever see plain ``str`` text, so new formats (EPUB, PDF) can be
added here later as separate parsers without touching reading or display code.

For the MVP only plain ``.txt`` is supported, using nothing but the standard
library so the app stays fully offline with no dependencies.
"""

from .loader import (
    load_book,
    load_book_full,
    find_books,
    book_title,
    LoadedBook,
    SUPPORTED_EXTENSIONS,
    BookLoadError,
)

__all__ = [
    "load_book",
    "load_book_full",
    "find_books",
    "book_title",
    "LoadedBook",
    "SUPPORTED_EXTENSIONS",
    "BookLoadError",
]
