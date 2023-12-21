from setuptools import setup, find_packages

setup(
    name="py-ssh3",
    version="0.1",
    description="Python SSH3 version",
    author="ElNiak",
    author_email="elniak@email.com",
    packages=find_packages(),
    install_requires=[
        "aiohttp",
        "pyOpenSSL",
        "cryptography",
        "aioquic",
        "http3",
        "authlib",
        "PyCryptodome"
    ],
)

