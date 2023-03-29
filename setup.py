from setuptools import setup, find_packages
import pathlib

# Get path to parent folder
here = pathlib.Path(__file__).parent.resolve()

# long_description = README.md
long_description = (here / 'README.md').read_text(encoding='utf-8')

'''
with open("README.md", "r") as fh:
    long_description = fh.read()
'''

github = 'https://github.com/N-Multifibra/netbox-proxbox'

# Proxbox dependencies
requires = [
    'poetry',
    'invoke',
    'requests>=2',
    'pynetbox>=5',
    'paramiko>=2',
    'proxmoxer>=1',
    'fastapi[all]',
    'starlette',
    'uvicorn[standard]',
    'websockets',
    'jinja2',
    'ujson>=5.7.0',
    'orjson>=3.8.9',
    'httpcore',
]

dev_requires = [
    'pytest>=3.7',
    'check-manifest',
    'twine',
    'setuptools',
    'wheel'
]

setup(
    name="netbox-proxbox",
    version="0.0.5",
    author="Emerson Felipe",
    author_email="emerson.felipe@nmultifibra.com.br",
    description="Integration between Proxmox and Netbox",
    url='https://github.com/N-Multifibra/netbox-proxbox',
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Framework :: Django",
        "Operating System :: Unix",
        "License :: OSI Approved :: Apache Software License",
    ],
    keywords="netbox netbox-plugin plugin proxmox proxmoxer pynetbox",
    project_urls={
        'Source': github,
    },
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "": ['*','*/*','*/*/*'],
    },
    install_requires=requires,
    extras_require={
        "dev": dev_requires,
    },
    python_requires= '>=3.9',
)
