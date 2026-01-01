# Contributing to MUXI Runtime

Thank you for your interest in contributing to MUXI Runtime! We're excited to have you join our community of developers building the future of AI infrastructure.

MUXI Runtime is the execution engine that powers AI agent formations. Your contributions help make AI development more accessible, reliable, and powerful for developers worldwide.

## 🤟 Anyone can cook :)

You can contribute by:

- [Reporting a bug](https://github.com/muxi-ai/runtime/issues/new/choose)
- [Participating in the discussions](https://muxi.org/community)
- [Improving the documentation](https://github.com/muxi-ai/docs)
- [Proposing new features](https://muxi.org/community)


## 👨🏼‍💻 Contributing code

If you're interested in contributing code, we welcome contributions from anyone who is motivated and wants to be part of that journey!

### 📜 Code of Conduct

We are committed to providing a welcoming and inclusive environment for all contributors. By participating in this project, you agree to:

- **Be respectful and inclusive** in all interactions
- **Welcome newcomers** and help them get started
- **Focus on constructive criticism** and helpful feedback
- **Respect differing viewpoints** and experiences
- **Accept responsibility** for mistakes and learn from them

See the full [code of conduct](CODE_OF_CONDUCT.md) for more details.

### 🚀 Getting started

#### Prerequisites

- Python 3.10 or higher
- Git
- A GitHub account
- API keys for at least one LLM provider (OpenAI, Anthropic, etc.)

#### Development Setup

1. **Fork the repository**
   ```bash
   # Go to https://github.com/muxi-ai/runtime
   # Click "Fork" button
   ```

2. **Clone your fork**
   ```bash
   git clone https://github.com/YOUR_USERNAME/runtime
   cd runtime
   ```

3. **Add upstream remote**
   ```bash
   git remote add upstream https://github.com/muxi-ai/runtime
   ```

4. **Create a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

5. **Install in development mode**
   ```bash
   pip install -e .[dev]
   ```

6. **Set up environment variables**
   ```bash
   # Create .env file
   cp .env.example .env

   # Add your API keys
   echo "OPENAI_API_KEY=your-key-here" >> .env
   echo "ANTHROPIC_API_KEY=your-key-here" >> .env
   ```

7. **Run tests to verify setup**
   ```bash
   pytest tests/e1e/day_1/test_1a1_basic_yaml_formation.py -v
   ```

### 🧪 Testing Philosophy

**We test against real services, not mocks.** This ensures our code works in production.

#### Running Tests

```bash
## Run all tests
pytest

## Run specific test suite
pytest tests/e1e/day_1/  # Foundation tests
pytest tests/e1e/day_2/  # Memory systems
pytest tests/e1e/day_3/  # Multimodal processing

## Run with verbose output
pytest -v

## Run with coverage
pytest --cov=muxi --cov-report=html
```

#### Test Organization

Tests are organized by feature "days" in our comprehensive test plan:
- **Day 1-3**: Core functionality (formation, memory, multimodal)
- **Day 4-6**: Integration features (MCP, file generation, knowledge)
- **Day 7-12**: Advanced features (workflow, resilience, clarification)

#### Writing Tests

```python
## Example test structure
async def test_feature_with_real_service():
    """Test description explaining what we're testing."""
    # 1. Setup - Create real formation
    formation = Formation()
    await formation.load("test-formations/test-config.yaml")

    # 2. Execute - Use real LLM/service
    overlord = await formation.start_overlord()
    response = await overlord.chat("test message", user_id="test123")

    # 3. Assert - Verify actual behavior
    assert response is not None
    assert "expected" in response.lower()
```

### 💻 Development Guidelines

#### Code Style

- **Python 3.10+ features** - Use modern Python
- **Type hints** - All public functions should have type hints
- **Docstrings** - Google-style docstrings for all public APIs
- **Black formatter** - 100 character line limit
- **Async/await** - All I/O operations must be async

```python
async def process_message(
    self,
    message: str,
    user_id: str,
    metadata: Optional[Dict[str, Any]] = None
) -> FormationResponse:
    """Process a user message through the formation.

    Args:
        message: The user's input message
        user_id: Unique identifier for the user
        metadata: Optional metadata for the request

    Returns:
        FormationResponse with the agent's response

    Raises:
        ConfigurationError: If formation is not properly configured
    """
    # Implementation here
```

#### Architecture Principles

1. **Formation-First** - Everything starts with YAML configuration
2. **Provider-Agnostic** - Use OneLLM for all LLM interactions
3. **Multi-User Isolation** - Always consider user context separation
4. **Fail Fast** - Clear errors for configuration problems
5. **Graceful Degradation** - Continue when optional features fail

#### Multilingual Support

**Always use LLM over pattern matching** for user-facing text:
- ❌ Don't: `if re.match(r'^(help|assist)', message)`
- ✅ Do: Use LLM to detect intent in any language

### 🔄 Pull Request Process

#### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
## or
git checkout -b fix/issue-description
```

#### 2. Make Your Changes

- Write clean, documented code
- Add tests for new functionality
- Update documentation if needed
- Ensure all tests pass

#### 3. Commit Your Changes

```bash
## Use clear, descriptive commit messages
git commit -m "Add support for custom memory backends"

## For multi-line commits
git commit -m "Fix memory leak in buffer manager

- Add cleanup in __del__ method
- Ensure connections are closed
- Add test for memory cleanup"
```

#### 4. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then go to GitHub and create a Pull Request with:
- **Clear title** describing the change
- **Description** of what and why
- **Link to issue** if applicable
- **Test results** showing tests pass

#### 5. PR Review Process

- Maintainers will review within 2-3 business days
- Address feedback constructively
- Once approved, we'll merge your contribution!

### 🐛 Reporting Issues

#### Bug Reports

Please include:
1. **Environment** (OS, Python version, installed packages)
2. **Formation YAML** that reproduces the issue
3. **Expected behavior** vs what actually happened
4. **Error messages** and stack traces
5. **Steps to reproduce**

#### Feature Requests

Please include:
1. **Use case** - What problem does this solve?
2. **Proposed solution** - How should it work?
3. **Alternatives considered** - Other approaches
4. **Impact** - Who benefits from this feature?

### 📚 Documentation

When adding features, please update:
- **Docstrings** in the code
- **README.md** if it's a major feature
- **Formation schema** if adding configuration options
- **Test documentation** for new test cases

### 🤝 Community

#### Getting Help

- **Discord**: [Join our Discord](https://discord.gg/muxi) for real-time chat
- **Discussions**: [GitHub Discussions](https://muxi.org/community) for questions
- **Issues**: [GitHub Issues](https://github.com/muxi-ai/runtime/issues) for bugs

#### Communication Tips

- Search existing issues/discussions before creating new ones
- Be patient - maintainers are often volunteers
- Provide context and be specific
- Follow up on your PRs and issues

### 🏗️ Project Structure

```
src/muxi/
├── formation/          # Formation loading and lifecycle
│   ├── overlord/      # Central orchestration
│   ├── agents/        # Agent implementations
│   ├── workflow/      # Task decomposition and SOPs
│   └── resilience/    # Error recovery
├── services/          # Core services
│   ├── llm/          # LLM integration (OneLLM)
│   ├── memory/       # Memory systems
│   ├── mcp/          # Tool protocol
│   └── a2a/          # Agent communication
└── utils/            # Shared utilities
```

### 📈 Performance Considerations

When contributing performance-sensitive code:
- Profile before and after changes
- Consider memory usage, not just speed
- Document performance characteristics
- Add benchmarks for critical paths

### 🚀 Release Process

We use semantic versioning (MAJOR.MINOR.PATCH):
- **PATCH**: Bug fixes, minor improvements
- **MINOR**: New features, backward compatible
- **MAJOR**: Breaking changes

Releases are automated through GitHub Actions when tags are pushed.

### 🙏 Recognition

Contributors are recognized in:
- Release notes
- Contributors file
- GitHub insights

We appreciate every contribution, no matter how small!

### 📄 License & Contributor Agreement

#### Contributor License Agreement (CLA)

By contributing to MUXI Runtime, you agree to our [Contributor License Agreement](CONTRIBUTOR_LICENSE_AGREEMENT.md):

1. **Grant of License**: You grant us permission to license your contributions on any terms we choose, including open-source and commercial licensing models.

2. **Purpose**: This allows your contributions to be included in the project and supports future development, including potential commercialization.

3. **Warranty**: Your contributions are provided "as is" without warranty.

**By submitting a pull request, you automatically agree to these terms.**

#### Project License

MUXI Runtime is licensed under the **Elastic License 2.0** (ELv2). This means:
- ✅ You can freely use, modify, and redistribute the software
- ✅ You can include it in commercial products
- ❌ You cannot offer it as a hosted/managed service to others

See [LICENSE](LICENSE) for full details.

---

**Thank you for contributing to MUXI Runtime! Together, we're building the future of AI infrastructure.**
