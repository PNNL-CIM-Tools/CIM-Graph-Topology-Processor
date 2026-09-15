"""Shared test setup: cim-graph reads its profile and namespace from the environment.

These must be set before any cimgraph module is imported, so they live here rather
than in a fixture.
"""
import os

os.environ.setdefault('CIMG_CIM_PROFILE', 'cimhub_2026')
os.environ.setdefault('CIMG_NAMESPACE', 'http://iec.ch/TC57/CIM100#')
