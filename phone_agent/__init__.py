"""
Phone Agent - An AI-powered phone automation framework.

This package provides tools for automating Android phone interactions
using AI models for visual understanding and decision making.
"""

from phone_agent.agent import PhoneAgent
from phone_agent.phone_pool import PhonePoolManager
from phone_agent.api import create_api_blueprint

__version__ = "0.1.0"
__all__ = ["PhoneAgent", "PhonePoolManager", "create_api_blueprint"]
