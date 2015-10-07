from setuptools import setup, find_packages

setup(
    name="coco-backends",
    description="Various coco backend contract implementations.",
    version="0.0.1",
    packages=find_packages('src'),
    package_dir={'': 'src'},
    namespace_packages=['coco'],
    install_requires=[
        'coco-contract',
        'docker-py==1.3.1',
        'passlib==1.6.5',
        'python-ldap==2.4.20',
        'requests==2.7.0'
    ],
)
