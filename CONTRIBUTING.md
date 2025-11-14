# Contributing to Obsidian MCP Server

Thank you for your interest in contributing!

## Development Setup

1. Clone the repository
2. Create a virtual environment: `python3 -m venv venv`
3. Activate it: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and configure
6. Run setup check: `python check_setup.py`

## Code Style

- Follow PEP 8
- Use type hints where appropriate
- Add docstrings to functions and classes
- Run `black` and `ruff` before committing

## Testing

- Run tests: `pytest tests/`
- Run specific test: `pytest tests/test_obsidian_tools.py`
- Check coverage: `pytest --cov=src tests/`

## Documentation

- Update relevant docs in `docs/` directory
- Keep README.md up to date
- Add examples for new features

## Pull Request Process

1. Create a feature branch
2. Make your changes
3. Ensure tests pass
4. Update documentation
5. Submit PR with clear description

## Questions?

Open an issue for discussion!
