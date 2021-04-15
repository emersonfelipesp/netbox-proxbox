from setuptools import setup, find_packages
import pathlib

# Get path to parent folder
here = pathlib.Path(__file__).parent.resolve()

# long_description = README.md
long_description = (here / 'README.md').read_text(encoding='utf-8')

# Proxbox dependencies
requires = [
    'python-dotenv',
    'poetry',
    'invoke',
    'numpy',
    'matplotlib',
    'requests>=2',
    'pynetbox>=5',
    'paramiko>=2',
    'proxmoxer>=1'

]

setup(
    name="netbox-proxbox",
    version="0.0.1",
    author="Emerson Pereira",
    author_email="emerson.felipe@nmultifibra.com.br",
    description="Integration between Proxmox and Netbox",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: Linux",
    ],
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=requires,
    python_requires= '>=3.6'
)
