import sys
sys.path.insert(0, '../..')
from src.muxi.runtime.overlord import Overlord  # noqa: E402
print('✅ Successfully imported Overlord!')
print('🔍 Checking if get_model_for_capability method exists...')
methods = [method for method in dir(Overlord) if 'capability' in method.lower()]
print(f'📋 Capability-related methods found: {methods}')
hasattr_check = hasattr(Overlord, 'get_model_for_capability')
print(f'🎯 get_model_for_capability method exists: {hasattr_check}')
