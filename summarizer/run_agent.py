
import argparse
import ast
import hashlib
import logging
import tokenize
from io import StringIO
from pathlib import Path

SKIP = {'.git', '.venv', 'venv', '__pycache__', 'node_modules'}


def describe_function(node):
    doc = ast.get_docstring(node)
    params = [
        arg.arg
        for arg in node.args.posonlyargs
        + node.args.args
        + node.args.kwonlyargs
    ]

    if node.args.vararg:
        params.append('*' + node.args.vararg.arg)

    if node.args.kwarg:
        params.append('**' + node.args.kwarg.arg)

    actions = []
    descendants = list(ast.walk(node))

    if any(
        isinstance(x, (ast.Return, ast.Yield, ast.YieldFrom))
        for x in descendants
    ):
        actions.append('returns or produces a value')

    if any(
        isinstance(x, (ast.For, ast.AsyncFor, ast.While))
        for x in descendants
    ):
        actions.append('uses iteration')

    if any(isinstance(x, ast.If) for x in descendants):
        actions.append('checks conditions')

    if any(
        isinstance(x, (ast.With, ast.AsyncWith))
        for x in descendants
    ):
        actions.append('uses a context manager')

    if any(
        isinstance(x, (ast.Try, ast.TryStar))
        for x in descendants
        if hasattr(ast, 'TryStar')
    ):
        actions.append('handles exceptions')

    detail = (
        doc.splitlines()[0].strip()
        if doc
        else 'No docstring; behavior inferred only from code structure.'
    )

    return (
        f"- {node.name}({', '.join(params)}): {detail}"
        + (
            f" Observed: {', '.join(actions)}."
            if actions
            else ''
        )
    )


def partial_syntax_summary(source, relative, error):
    """
    Attempt to recover basic declarations from invalid Python.

    The recovered information is unverified and must not be
    treated as a successful analysis.
    """

    lines = [
        f'File: {relative}',
        (
            f'ERROR: SyntaxError at line {error.lineno}, '
            f'column {error.offset}: {error.msg}'
        ),
        'PARTIAL RECOVERY (unverified): The file could not be parsed.',
        (
            'The following are possible top-level declarations, '
            'not validated Python definitions:'
        ),
    ]

    recovered = []

    # Tokenization helps avoid identifying declarations
    # inside comments or string literals.
    tokens = []

    try:
        for token in tokenize.generate_tokens(
            StringIO(source).readline
        ):
            tokens.append(token)

    except (tokenize.TokenError, IndentationError):
        # Preserve tokens collected before the error.
        pass

    significant = [
        token
        for token in tokens
        if token.type not in (
            tokenize.ENCODING,
            tokenize.NL,
            tokenize.COMMENT,
        )
    ]

    for i, token in enumerate(significant):

        # Only look for declarations at column zero.
        if token.start[1] != 0 or token.type != tokenize.NAME:
            continue

        if token.string in ('def', 'class'):

            if i + 1 < len(significant):
                next_token = significant[i + 1]

                if (
                    next_token.type == tokenize.NAME
                    and next_token.start[0] == token.start[0]
                ):
                    kind = (
                        'function'
                        if token.string == 'def'
                        else 'class'
                    )

                    recovered.append(
                        f'- Possible {kind}: '
                        f'{next_token.string} '
                        f'(line {token.start[0]})'
                    )

        elif token.string == 'async' and i + 2 < len(significant):

            def_token, name_token = significant[i + 1:i + 3]

            if (
                def_token.string == 'def'
                and name_token.type == tokenize.NAME
                and def_token.start[0] == token.start[0]
                and name_token.start[0] == token.start[0]
            ):
                recovered.append(
                    f'- Possible async function: '
                    f'{name_token.string} '
                    f'(line {token.start[0]})'
                )

        elif token.string in ('import', 'from'):

            recovered.append(
                f'- Possible import statement '
                f'(line {token.start[0]})'
            )

    if recovered:
        lines.extend(recovered)
    else:
        lines.append('- No reliable declarations recovered.')

    lines.append(
        'Note: Partial recovery does not verify signatures, '
        'behavior, or correctness. File remains an error.'
    )

    return '\n'.join(lines)


def inspect_file(path, root):
    relative = path.relative_to(root).as_posix()

    try:
        raw = path.read_bytes()

        if len(raw) > 1024 * 1024:
            return {
                'file': relative,
                'status': 'error',
                'summary': 'File exceeds 1 MiB safety limit.',
            }

        source = raw.decode('utf-8-sig')

        try:
            tree = ast.parse(source, filename=relative)

        except SyntaxError as exc:
            return {
                'file': relative,
                'status': 'error',
                'summary': partial_syntax_summary(
                    source, relative, exc
                ),
            }

        imports = sorted(
            {
                alias.name
                for n in ast.walk(tree)
                if isinstance(n, ast.Import)
                for alias in n.names
            }
            |
            {
                '.' * n.level + (n.module or '')
                for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom)
            }
        )

        funcs = [
            n
            for n in tree.body
            if isinstance(
                n, (ast.FunctionDef, ast.AsyncFunctionDef)
            )
        ]

        classes = [
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef)
        ]

        doc = ast.get_docstring(tree)

        lines = [
            f'File: {relative}',
            f'SHA256: {hashlib.sha256(raw).hexdigest()}',
            (
                f"Purpose: {doc.splitlines()[0]}"
                if doc
                else (
                    'Purpose: No module description provided; '
                    'summary based on structure.'
                )
            ),
            (
                f"Imports: {', '.join(imports)}"
                if imports
                else 'Imports: none'
            ),
            'Functions:',
        ]

        lines += [
            describe_function(n)
            for n in funcs
        ] or ['- none']

        lines.append('Classes:')

        lines += [
            (
                f"- {c.name}: "
                f"{ast.get_docstring(c).splitlines()[0] if ast.get_docstring(c) else 'No class docstring.'} "
                f"Methods: "
                f"{', '.join(n.name for n in c.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))) or 'none'}"
            )
            for c in classes
        ] or ['- none']

        lines.append(
            'Note: Static analysis only; '
            'runtime behavior is not verified.'
        )

        return {
            'file': relative,
            'status': 'ok',
            'summary': '\n'.join(lines),
        }

    except (
        OSError,
        UnicodeError,
        ValueError,
        RecursionError,
    ) as exc:

        return {
            'file': relative,
            'status': 'error',
            'summary': (
                f'Unable to fully analyze: '
                f'{type(exc).__name__}: {exc}. '
                f'No guessed corrections were made.'
            ),
        }


def write_pdf(text, destination):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
        )
        from xml.sax.saxutils import escape

    except ImportError as exc:
        raise RuntimeError(
            'PDF output requires: pip install reportlab'
        ) from exc

    styles = getSampleStyleSheet()

    story = [
        Paragraph('Summarizer Report', styles['Title']),
        Spacer(1, 12),
    ]

    for block in text.split('\n\n'):
        for line in block.splitlines():
            story.append(
                Paragraph(escape(line), styles['Normal'])
            )
            story.append(Spacer(1, 5))

        story.append(Spacer(1, 10))

    SimpleDocTemplate(
        str(destination),
        pagesize=letter,
    ).build(story)


def main():
    parser = argparse.ArgumentParser(
        description='Offline Python code summarizer'
    )

    parser.add_argument(
        '--target',
        required=True,
        help='Python file or repository directory',
    )

    parser.add_argument(
        '--max-steps',
        type=int,
        default=15,
        help='Maximum number of files to analyze',
    )

    parser.add_argument(
        '--format',
        choices=['text', 'pdf'],
        default='text',
    )

    parser.add_argument(
        '--output',
        default=None,
    )

    parser.add_argument(
        '--log-file',
        default='./logs/agent.log',
    )

    args = parser.parse_args()

    if args.max_steps < 1:
        parser.error('--max-steps must be at least 1')

    target = Path(args.target).resolve()

    if not target.exists() or not (
        target.is_dir()
        or (
            target.is_file()
            and target.suffix == '.py'
        )
    ):
        parser.error(
            '--target must be an existing directory or Python file'
        )

    log_file = Path(args.log_file)
    log_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(levelname)s %(message)s',
        filemode='w',
    )

    root = (
        target
        if target.is_dir()
        else target.parent
    )

    if target.is_file():
        paths = [target]
    else:
        paths = sorted(
            p
            for p in target.rglob('*.py')
            if not any(
                part in SKIP
                for part in p.relative_to(target).parts
            )
        )

    results = []

    for path in paths[:args.max_steps]:
        result = inspect_file(path, root)
        results.append(result)

        logging.info(
            '%s %s',
            result['status'],
            result['file'],
        )

    omitted = [
        p.relative_to(root).as_posix()
        for p in paths[args.max_steps:]
    ]

    ok = sum(
        r['status'] == 'ok'
        for r in results
    )

    errors = len(results) - ok

    complete = not omitted and errors == 0

    header = (
        'Summarizer Agent Report\n'
        f'Files discovered: {len(paths)} | '
        f'Checked: {len(results)} | '
        f'Successful: {ok} | '
        f'Errors: {errors} | '
        f'Omitted: {len(omitted)}\n'
        f"Validation: {'COMPLETE' if complete else 'INCOMPLETE'}"
    )

    if omitted:
        header += (
            '\nNot checked due to max-steps: '
            + ', '.join(omitted)
        )

    report = (
        header
        + '\n\n'
        + '\n\n'.join(
            r['summary']
            for r in results
        )
    )

    output = Path(
        args.output
        or (
            'summary.pdf'
            if args.format == 'pdf'
            else 'summary.txt'
        )
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if args.format == 'pdf':
        write_pdf(report, output)
    else:
        output.write_text(
            report + '\n',
            encoding='utf-8',
        )

    logging.info(
        'discovered=%d checked=%d errors=%d '
        'omitted=%d complete=%s',
        len(paths),
        len(results),
        errors,
        len(omitted),
        complete,
    )

    print(report.split('\n\n')[0])

    # Part 4 improvement:
    # Display specific errors directly in the terminal.
    for result in results:
        if result['status'] == 'error':
            print(
                f"\nERROR in {result['file']}:"
            )
            print(result['summary'])

    print(f'\nReport saved: {output}')

    return 0 if complete else 1


if __name__ == '__main__':
    raise SystemExit(main())