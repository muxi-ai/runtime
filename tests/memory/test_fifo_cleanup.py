# To run this test:
# PYTHONPATH=/Users/ran/Projects/muxi/code/runtime python tests/memory/test_fifo_cleanup.py
import asyncio
import time
from src.muxi.runtime.memory.short_term import ShortTermMemory


async def test_fifo_cleanup():
    print('Creating ShortTermMemory with 0.01MB limit...')
    # Create with very small memory limit to trigger cleanup
    buffer = ShortTermMemory(
        max_size=5,
        buffer_multiplier=10,
        max_memory_mb=0.01,  # Very small limit (0.01MB = 10KB)
        fifo_interval_min=0.1  # Check every 6 seconds for faster testing
    )

    print('Adding content to trigger memory cleanup...')

    # Add lots of content to exceed the 0.01MB limit
    for i in range(20):
        # Add large text content to quickly exceed memory limit
        large_text = f'This is test message {i}. ' * 100  # About 2KB per message
        await buffer.add(large_text, {'message_id': i, 'type': 'test'})
        print(f'Added message {i}, buffer length: {len(buffer.buffer)}')

        # Check current memory estimate
        if i % 5 == 0:
            stats = buffer.get_stats()
            print(f'Buffer stats: {stats}')

    print('Waiting to see cleanup in action...')
    # Wait a bit to see the cleanup task run
    time.sleep(15)

    final_stats = buffer.get_stats()
    print(f'Final buffer stats: {final_stats}')
    print('✓ FIFO cleanup test completed')


if __name__ == "__main__":
    # Run the test
    asyncio.run(test_fifo_cleanup())
