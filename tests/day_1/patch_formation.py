"""
Monkey patch for Formation class to fix SecretsManager initialization bug.

This is a temporary fix for testing until the bug is fixed in the main code.
"""
import os
from muxi.runtime.formation import Formation
from muxi.runtime.services.secrets import SecretsManager

# Save original load method
_original_load = Formation.load

def patched_load(self, config_path: str) -> None:
    """Patched load method that fixes SecretsManager initialization"""
    # Call original method but catch the specific part
    try:
        _original_load(self, config_path)
    except Exception as e:
        # If it's the SecretsManager issue, fix it
        if "File exists" in str(e) and hasattr(self, '_formation_path'):
            # Get the directory path
            if os.path.isfile(self._formation_path):
                formation_dir = os.path.dirname(self._formation_path)
            else:
                formation_dir = self._formation_path
            
            # Reinitialize SecretsManager with correct path
            self.secrets_manager = SecretsManager(formation_dir)
            
            # Try loading again with fixed path
            _original_load(self, config_path)
        else:
            raise

# Apply monkey patch
Formation.load = patched_load