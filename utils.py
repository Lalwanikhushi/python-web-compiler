"""Utility functions for Python compilation and execution."""

import os
import sys
import io
import traceback
import py_compile
from contextlib import redirect_stdout, redirect_stderr
import logging

logger = logging.getLogger(__name__)

def sanitize_python_code(code):
    """
    Remove potentially harmful code patterns.
    This is a basic implementation and not a complete security solution.
    """
    # List of dangerous functions/imports
    dangerous_patterns = [
        'os.system(',
        'subprocess',
        'eval(',
        'exec(',
        '__import__(',
        'importlib',
        'open(',
        'file(',
        'globals(',
        'locals(',
        'compile(',
    ]
    
    for pattern in dangerous_patterns:
        if pattern in code:
            return False, f"Potentially unsafe code detected: {pattern}"
    
    return True, code

def get_file_content(filepath):
    """Get the content of a file."""
    try:
        with open(filepath, 'r') as file:
            return file.read()
    except Exception as e:
        logger.error(f"Error reading file {filepath}: {e}")
        return None

def format_traceback(tb):
    """Format a traceback for display."""
    lines = tb.split('\n')
    # Remove file paths that might reveal system information
    formatted_lines = []
    for line in lines:
        if line.strip():
            formatted_lines.append(line)
    return '\n'.join(formatted_lines)

def format_syntax_error(error_message):
    """Format syntax error message for display."""
    lines = error_message.split('\n')
    formatted_lines = []
    
    for line in lines:
        # Skip lines with system paths
        if "File " in line and "/" in line:
            parts = line.split('"')
            if len(parts) >= 3:
                filename = os.path.basename(parts[1])
                formatted_lines.append(f'  File "{filename}"{parts[2]}')
        else:
            formatted_lines.append(line)
            
    return '\n'.join(formatted_lines)
