# Use setuptools if we can
try:
    from setuptools.core import setup
except ImportError:
    from distutils.core import setup

PACKAGE = 'django-moreviews'
VERSION = '0.1'

setup(
    name=PACKAGE, version=VERSION,
    description="Django class-based views that complement the built-in ones.",
    packages=[ 'moreviews' ],
    license='MIT',
    author='Art Discovery Ltd',
    maintainer='James Aylett',
    maintainer_email='james@tartarus.org',
    url = 'http://tartarus.org/james/computers/django/',
)
