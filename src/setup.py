import os
from setuptools import setup, find_packages

# Read version from .version file in the runtime package
with open(os.path.join(os.path.dirname(__file__), 'src/muxi/runtime', '.version'), 'r') as f:
    version = f.read().strip()

setup(
    name="muxi-runtime",
    version=version,
    description="MUXI Runtime",
    author="Ran Aroussi",
    author_email="ran@aroussi.com",
    packages=find_packages(),
    install_requires=[
        "loguru",
        "pydantic",
        "onellm>=0.1.0",
        "faiss-cpu",
        "numpy>=1.20.0",
        "markitdown[all]>=0.1.0",
    ],
    project_urls={
        "Source": "https://github.com/muxi-ai/runtime",
        "Bug Reports": "https://github.com/muxi-ai/runtime/issues",
        "Documentation": "https://github.com/muxi-ai/runtime",
        "Changelog": "https://github.com/muxi-ai/runtime/blob/main/CHANGELOG.md",
        "Funding": "https://github.com/sponsors/ranaroussi",
    },
    python_requires=">=3.10"
)
