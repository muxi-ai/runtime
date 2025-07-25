import sys
import traceback

# Set up import path before importing muxi modules
sys.path.insert(0, 'runtime')

from src.muxi.knowledge.handler import KnowledgeHandler  # noqa: E402

try:
    handler = KnowledgeHandler(
        agent_id_or_sources='test_agent',
        embedding_dimension=1536,
        mode='local'
    )
    print('✓ KnowledgeHandler instantiated successfully')
except Exception as e:
    print(f'❌ Error: {e}')
    traceback.print_exc()
