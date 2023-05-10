from setuptools import find_packages, setup

PACKAGE_NAME = "librarian"

with open(f"{PACKAGE_NAME}/version.txt") as ifp:
    VERSION = ifp.read().strip()

long_description = ""
with open("README.md") as ifp:
    long_description = ifp.read()

setup(
    name=PACKAGE_NAME,
    version=VERSION,
    packages=find_packages(),
    install_requires=[
        "aiohttp",
        "bugout",
        "pydantic",
        "langchain",
        "openai",
        "faiss-cpu",
        "tiktoken",
    ],
    extras_require={
        "dev": [
            "black",
            "mypy",
            "isort",
        ],
        "distribute": ["setuptools", "twine", "wheel"],
    },
    description="Moonstream discord bots",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Moonstream",
    author_email="engineering@moonstream.to",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python",
        "License :: OSI Approved :: Apache Software License",
        "Topic :: Software Development :: Libraries",
    ],
    python_requires=">=3.8",
    url="https://github.com/bugout-dev/discord-bots",
    entry_points={
        "console_scripts": [
            "librarian=librarian.cli:main",
        ]
    },
    include_package_data=True,
)
