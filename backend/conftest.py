# conftest.py — makes the backend package root importable during pytest
import sys
import os

# Add backend/ directory to sys.path so `from nlp.xxx import yyy` works
sys.path.insert(0, os.path.dirname(__file__))
