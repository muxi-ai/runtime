"""
Debug the AsyncOperationResult issue
"""
import asyncio
from muxi.utils.async_operation_manager import execute_with_timeout
from muxi.datatypes.async_operations import OperationStatus


async def test_execute_with_timeout():
    """Test execute_with_timeout directly"""

    async def successful_operation():
        """A simple operation that returns data"""
        return {"test": "data", "value": 123}

    result = await execute_with_timeout(
        successful_operation,
        operation_type="test",
        description="Test operation",
        timeout=5.0
    )

    print(f"\nResult details:")
    print(f"  operation_id: {result.operation_id}")
    print(f"  status: {result.status}")
    print(f"  status type: {type(result.status)}")
    print(f"  status == OperationStatus.COMPLETED: {result.status == OperationStatus.COMPLETED}")
    print(f"  result: {result.result}")
    print(f"  error: {result.error}")
    print(f"  is_success: {result.is_success}")
    print(f"  elapsed_time: {result.elapsed_time}")

    return result


if __name__ == "__main__":
    result = asyncio.run(test_execute_with_timeout())
    print(f"\nFinal: is_success = {result.is_success}")
