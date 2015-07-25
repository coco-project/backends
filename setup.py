from setuptools import setup, find_packages

setup(
    name="ipynbsrv-backends",
    description="Various ipynbsrv backend contract implementations.",
    version="0.0.1",
    packages=find_packages('src'),
    package_dir={'': 'src'},
    namespace_packages=['ipynbsrv'],
    install_requires=[
        'docker-py==1.3.1',
        'ipynbsrv-contract',
        'requests==2.7.0',
        'python-ldap==2.4.20'
    ],
)
