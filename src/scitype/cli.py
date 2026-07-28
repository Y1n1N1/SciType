"""Terminal interface for SciType V0.1."""

import sys

from .dictionary import DictionaryError, load_dictionary
from .engine import parse_text


def main() -> int:
    """Start the interactive terminal parser."""
    try:
        dictionary = load_dictionary()
    except DictionaryError as error:
        print(f"SciType 启动失败：{error}", file=sys.stderr)
        return 1

    print("SciType V0.1")
    print("输入缩写并按回车，按 Ctrl+C 退出。")

    while True:
        try:
            text = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        print(parse_text(text, dictionary))
