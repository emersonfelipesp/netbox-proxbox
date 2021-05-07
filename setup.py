from setuptools import setup, find_packages
import pathlib

# Get path to parent folder
here = pathlib.Path(__file__).parent.resolve()

# long_description = README.md
long_description = (here / 'README.md').read_text(encoding='utf-8')

# Proxbox dependencies
requires = [
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
    version="0.0.3.dev1",
    author="Emerson Pereira",
    author_email="emerson.felipe@nmultifibra.com.br",
    description="Integration between Proxmox and Netbox",
    url='https://github.com/N-Multifibra/netbox-proxbox',
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: Linux",
        "License :: OSI Approved :: Apache Software License",
    ],
    keywords="netbox netbox-plugin plugin proxmox proxmoxer pynetbox",
    project_urls={
        'Source': 'https://github.com/N-Multifibra/netbox-proxbox',
    },
    packages=find_packages(),
    install_requires=requires,
    python_requires= '>=3.6',
    package_data={
        '': ['*.html'],
        'netbox_proxbox.api': ['*','*/*','*/*/*'],
        'netbox_proxbox.templates': ['*','*/*','*/*/*'],
    },
)
