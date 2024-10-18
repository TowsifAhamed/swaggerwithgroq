from setuptools import setup, find_packages

setup(
    name='swaggerwithgroq',
    version='0.1.0',
    packages=find_packages(),
    install_requires=[
        'requests',
        'pyyaml',
        'groq', 
    ],
    description='Generate realistic API data from Swagger json using Groq',
    author='Towsif Ahamed Labib',
    author_email='towsif.kuet.ac.bd@gmail.com',
    url='https://github.com/TowsifAhamed/swaggerwithgroq/',
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
    ],
)
