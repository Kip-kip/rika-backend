from setuptools import setup, find_packages

setup(
    name="rika_backend",
    versions={
        "release": "0.1.0",
        "type": "development",
    },
    author="Tiberbu",
    author_email="dev@tiberbu.com",
    description="Rika shared core — Frappe app (Lead/Quotation/Project, pricing engine, auth, M-Pesa)",
    license="MIT",
    packages=find_packages(),
    zip_safe=False,
)
