__version__ = '2.0.31'

import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()

setuptools.setup(name='roboger',
                 version=__version__,
                 author='Altertech',
                 author_email='pr@altertech.com',
                 description='Roboger server',
                 long_description=long_description,
                 long_description_content_type='text/markdown',
                 url='https://github.com/alttch/roboger',
                 packages=setuptools.find_packages(),
                 license='Apache License 2.0',
                 install_requires=[
                     'requests', 'pyyaml', 'sqlalchemy', 'pyaltt2>=0.0.61',
                     'flask', 'flask-restx', 'jsonschema', 'python-rapidjson',
                     'netaddr', 'filetype', 'tebot', 'simplejson',
                     'werkzeug==0.16.1', 'python-magic'
                 ],
                 classifiers=(
                     'Programming Language :: Python :: 3',
                     'License :: OSI Approved :: Apache Software License',
                     'Topic :: Communications',
                 ),
                 scripts=['bin/roboger-control'])
