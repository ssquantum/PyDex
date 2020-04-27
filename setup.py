"""Setup script for PyDex using setuptools"""
from setuptools import setup, find_packages

setup(name = 'PyDex',
        version = "0.0",
        packages = find_packages(),
        # setup_requires=[],
        install_requires = ['pip>=7.0',
                            'astropy>=2.0.12-3',
                            'numpy>=1.11',
                            'logging>=0.5.1.2',
                            'colorlog>=4.0.2',
                            'scipy>=1.1.0-4',
                            'pyqtgraph>=0.10.0',
                            'pyqt5>=5.7.1-1',
                            'xmltodict>=0.12.0',
                            'nidaqmx>=0.5.7-1',
                            'pywin32>=220.0.0-4',
                            're>=2.2.1',
                            'scikit-image>=0.16.2'],
        # tests_require=['pytest','setuptools>=26'],
        # package_data = {
        #     # If any package contains *.txt or *.rst files, include them:
        #     '': ['*.txt','*.md'],
        # },
        author = 'Stefan Spence',
        author_email = 's.j.spence@durham.ac.uk',
        description = 'PyDex: Experimental control and analysis interface',
        # license = '',
        keywords = 'automated single atom experiment quantum',
        url = 'https://github.com/ssquantum/PyDex/'
        )