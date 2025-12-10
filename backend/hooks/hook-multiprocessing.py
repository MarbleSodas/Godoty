"""Runtime hook for multiprocessing support in PyInstaller."""
import sys
import os
import multiprocessing

# Fix for multiprocessing in PyInstaller
if getattr(sys, 'frozen', False):
    # Running in a bundle
    multiprocessing.freeze_support()

    # Set the executable path for spawned processes
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller sets _MEIPASS to the temp folder where files are extracted
        os.environ['_MEIPASS'] = sys._MEIPASS
