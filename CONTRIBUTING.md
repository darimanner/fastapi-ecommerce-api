# Contributing

Thanks for taking a look. Issues and pull requests are welcome.

## Setup

You need Python 3.14, [uv](https://docs.astral.sh/uv/), Docker and make.

```bash
make install        # dependencies and git hooks
cp .env.example .env
make up             # PostgreSQL
make migrate
```

## Before you open a pull request

```bash
make check          # ruff, mypy, lock check, file hygiene
make test           # needs Docker, fails below 85% coverage
```

## Workflow

- Branch from `main`, one topic per branch.
- Keep commits small, with messages in the imperative mood in the [Conventional Commits](https://www.conventionalcommits.org/) style, for example `feat: add product variants`.
- Open a pull request against `main`. CI must pass; pull requests are squash-merged.
- Architecture changes come with an ADR in `docs/adr/`, see the [template](docs/adr/template.md).
