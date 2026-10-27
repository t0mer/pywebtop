from setuptools import setup, find_packages
from pathlib import Path

BASE_DIR = Path(__file__).parent
readme_path = BASE_DIR / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

setup(
    name="pywebtop",
    version="0.0.2",
    description="Unofficial async Python API wrapper for Webtop (SmartSchool)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="MIT",
    author="Tomer Klein",
    author_email="tomer.klein@gmail.com",
    url="https://github.com/t0mer/pywebtop",
    download_url="https://pypi.org/project/pywebtop/",
    packages=find_packages(exclude=("tests",)),
    python_requires=">=3.8",
    install_requires=[
        "httpx>=0.25,<1.0",
    ],
    entry_points={
        "console_scripts": [
            "webtop=webtop.cli:main",
        ],
    },
    keywords=["webtop", "smartschool", "education", "api", "async"],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Education",
        "Topic :: Software Development :: Libraries",
        "Framework :: AsyncIO",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
    ],
)
