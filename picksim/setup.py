from setuptools import setup, find_packages

setup(
    name="picksim",
    version="0.1.0",
    description="NFL Survivor Pool Pick Optimizer using FPI data",
    author="Jake Selvey",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=[
        "pandas>=1.3.0",
        "numpy>=1.21.0",
    ],
    extras_require={
        "dev": [
            "jupyter>=1.0.0",
            "matplotlib>=3.4.0",
            "seaborn>=0.11.0",
            "reportlab>=3.6.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "picksim-filter=scripts.generate_filtered_table:generate_filtered_table",
            "picksim-analyze=scripts.analyze_entries:analyze_entries",
        ]
    }
)
