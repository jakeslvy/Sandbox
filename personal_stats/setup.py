from setuptools import setup, find_packages

setup(
    name="personal_stats",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        'pandas',
        'numpy',
        'duckdb',
        'python-dotenv',
        'matplotlib',
        'scikit-learn',
        'scipy',
        'gspread',  # if you're using this for Google Sheets
        # add any other packages you're using
    ]
)