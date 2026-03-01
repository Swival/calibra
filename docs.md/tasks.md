# Writing Tasks

Tasks are the unit of work in a Calibra campaign. Each task gives the agent a prompt, an initial workspace, and optionally a way to verify the result.

## Task directory structure

```
tasks/my-task/
  task.md       # Prompt sent to the agent (required)
  env/          # Initial workspace files (required, can be empty)
  verify.sh     # Verification script (optional)
  meta.toml     # Task metadata (optional)
```

## task.md: the prompt

This is the exact text sent to the coding agent. Write it the way you'd describe a task to a developer: clear, specific, and self-contained.

A simple generation task might look like:

```markdown
Write a Python script called `hello.py` that prints "Hello, World!" to stdout.
```

A bug fix:

```markdown
Fix the typo in main.py: 'pritn' should be 'print'.
```

Something more involved:

```markdown
The file `api.py` has a SQL injection vulnerability in the `get_user` function.
The user ID parameter is interpolated directly into the query string.

Fix this by using parameterized queries. Do not change the function signature
or return type. The existing tests in `test_api.py` should still pass.
```

Good prompts are specific about what files to create or modify, state the expected behavior clearly, and mention constraints like "don't change the API" or "keep tests passing." Since the agent can't ask clarifying questions, avoid ambiguity.

## env/: the workspace

The `env/` directory contains the initial files placed in the agent's working directory before it starts. It's required but can be empty for tasks where the agent creates everything from scratch.

An empty workspace (agent creates files):

```
tasks/hello-world/
  task.md
  env/          # empty
  verify.sh
```

A pre-populated workspace (agent modifies existing files):

```
tasks/fix-typo/
  task.md
  env/
    main.py     # contains the typo to fix
  verify.sh
```

A larger workspace:

```
tasks/refactor-api/
  task.md
  env/
    src/
      api.py
      models.py
      utils.py
    tests/
      test_api.py
    requirements.txt
  verify.sh
```

The entire `env/` tree is copied into a temporary directory for each trial, so the original files are never modified.

## verify.sh: the verifier

An optional executable shell script that checks whether the agent succeeded. Calibra runs it in the trial's workspace directory after the agent finishes. Exit code 0 means pass, anything else means fail. The script has a 30-second timeout. If `verify.sh` is not present, the trial won't have a `verified` field and pass rates can't be computed.

When a campaign has a `[reviewer]` configured, `verify.sh` is skipped — the reviewer determines pass/fail instead. Tasks can include both `verify.sh` and be used with reviewer campaigns; the campaign config controls which verification method is used.

Make sure the script is executable:

```bash
chmod +x tasks/my-task/verify.sh
```

Here's a verifier that checks output:

```bash
#!/bin/sh
python3 hello.py | grep -qx "Hello, World!"
```

One that checks file contents:

```bash
#!/bin/sh
! grep -q 'pritn' main.py && python3 main.py
```

One that runs a test suite:

```bash
#!/bin/sh
python3 -m pytest tests/ -q --tb=no
```

And one with multiple checks:

```bash
#!/bin/sh
set -e

# File must exist
test -f output.json

# Must be valid JSON
python3 -c "import json; json.load(open('output.json'))"

# Must contain expected key
python3 -c "
import json
data = json.load(open('output.json'))
assert 'results' in data
assert len(data['results']) > 0
"
```

Use `set -e` when chaining multiple checks so the first failure stops execution. Keep verifiers fast; they have a 30-second timeout. Test your verifier manually before running a campaign. Use `grep -q` for silent matching (no output, just exit code). And avoid checking for exact formatting when the semantics are what actually matter.

## meta.toml: task metadata

An optional TOML file for arbitrary metadata about the task. Calibra loads it but doesn't enforce any schema, so you can use it however you like: categorization, difficulty ratings, tags, or any other annotations.

```toml
[meta]
difficulty = "easy"
category = "generation"
language = "python"
estimated_turns = 3

[tags]
skills = ["file-creation", "stdout"]
```

The metadata is available in trial reports and can be useful for post-hoc analysis.

## Task discovery

Calibra discovers tasks by scanning the `tasks_dir` specified in your campaign config. The scan is alphabetical, and every subdirectory must be a valid task. If any task fails validation, the entire campaign is rejected.

A task is valid when `task.md` exists and is non-empty, `env/` exists and is a directory, and (if present) `verify.sh` is executable. You can organize tasks into subdirectories if needed, but the scanner only looks one level deep (direct children of `tasks_dir`).

## Real-world task examples

### Code generation

```
tasks/fibonacci/
  task.md       →  "Write fib.py that prints the first 20 Fibonacci numbers,
                     one per line."
  env/          →  (empty)
  verify.sh     →  python3 fib.py | head -5 | grep -qx "0\n1\n1\n2\n3"
```

### Bug fixing

```
tasks/off-by-one/
  task.md       →  "The function count_words in counter.py has an off-by-one
                     error. Fix it so the tests pass."
  env/
    counter.py  →  (buggy implementation)
    test_counter.py → (tests that expose the bug)
  verify.sh     →  python3 -m pytest test_counter.py -q --tb=no
```

### Refactoring

```
tasks/extract-function/
  task.md       →  "The process_data function in etl.py is too long.
                     Extract the validation logic into a separate
                     validate_record function. Keep all tests passing."
  env/
    etl.py
    test_etl.py
  verify.sh     →  python3 -m pytest test_etl.py -q --tb=no &&
                    grep -q 'def validate_record' etl.py
```

### Multi-file tasks

```
tasks/add-endpoint/
  task.md       →  "Add a DELETE /users/{id} endpoint to the Flask app.
                     It should return 204 on success and 404 if the user
                     doesn't exist. Add tests."
  env/
    app.py
    models.py
    test_app.py
    requirements.txt
  verify.sh     →  pip install -r requirements.txt -q &&
                    python3 -m pytest test_app.py -q --tb=short
```
