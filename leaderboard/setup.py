from setuptools import find_packages, setup

with open("leaderboard/version.txt") as ifp:
    VERSION = ifp.read().strip()

long_description = ""
with open("README.md") as ifp:
    long_description = ifp.read()

setup(
    name="leaderboard-bot",
    version=VERSION,
    packages=find_packages(),
    install_requires=[
        "discord.py",
        "requests",
        "pydantic",
    ],
    extras_require={
        "dev": ["black", "isort", "mypy", "types-requests", "types-python-dateutil"],
    },
    package_data={"machine": ["py.typed"]},
    zip_safe=False,
    description="Moonstream leaderboard bot.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="moonstream.to",
    author_email="engineering@moonstream.to",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python",
        "License :: OSI Approved :: Apache Software License",
        "Topic :: Software Development :: Libraries",
    ],
    url="https://github.com/moonstream-to/discord-bots/leaderboard",
    python_requires=">=3.10",
    entry_points={"console_scripts": ["leaderboard=leaderboard.cli:main"]},
)
