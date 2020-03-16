__version__ = '2.0.2'

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
                     'requests', 'pyyaml', 'sqlalchemy', 'pyaltt2', 'flask',
                     'jsonschema', 'python-rapidjson', 'netaddr', 'filetype',
                     'tebot', 'simplejson'
                 ],
                 classifiers=(
                     'Programming Language :: Python :: 3',
                     'License :: OSI Approved :: Apache Software License',
                     'Topic :: Communications',
                 ),
                 scripts=['bin/roboger-control'])
