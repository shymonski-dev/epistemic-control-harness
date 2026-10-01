"""Load explicitly requested key=value settings without executing shell code."""
import os
from pathlib import Path
import shlex

ALLOWED = {'OPENROUTER_API_KEY', 'OPENROUTER_BASE_URL', 'LM_STUDIO_API_KEY',
           'LM_STUDIO_BASE_URL', 'GENERATOR_MODEL', 'VERIFIER_MODEL', 'REWRITER_MODEL',
           'INDEPENDENT_VERIFIER_MODEL'}


def load_env_file(path: Path) -> None:
    entries = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].strip()
        name, sep, value = line.partition('=')
        name = name.strip()
        if not sep or name not in ALLOWED:
            raise ValueError(f'Unsupported environment setting on line {number}')
        try:
            tokens = shlex.split(value.strip(), comments=True, posix=True)
        except ValueError:
            raise ValueError(f'Invalid quoting on environment line {number}') from None
        if len(tokens) > 1:
            raise ValueError(f'Environment value must be one token on line {number}')
        entries[name] = tokens[0] if tokens else ''
    # Existing process environment takes precedence. Never execute expansions.
    for name, value in entries.items():
        os.environ.setdefault(name, value)
