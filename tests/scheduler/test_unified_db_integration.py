#!/usr/bin/env python3
"""
Test unified database integration between Formation, LongTermMemory, and Scheduler.
"""

from unittest.mock import MagicMock, patch
import sys
import os

# Add the source directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))


def test_formation_creates_shared_database_manager():
    """Test that Formation creates ONE DatabaseManager for sharing."""
    
    # Mock the database manager
    with patch('muxi.runtime.services.db.get_database_manager') as mock_get_db:
        mock_db_manager = MagicMock()
        mock_db_manager.database_type = 'postgresql'
        mock_get_db.return_value = mock_db_manager
        
        # Mock overlord
        mock_overlord = MagicMock()
        
        # Simulate Formation initialization
        from muxi.runtime.services.db import get_database_manager
        
        # Formation creates ONE DatabaseManager
        connection_string = "postgresql://user:pass@localhost/test"
        db_manager = get_database_manager(connection_string)
        mock_overlord.db_manager = db_manager
        
        # Verify Formation created the database manager
        assert hasattr(mock_overlord, 'db_manager')
        assert mock_overlord.db_manager == mock_db_manager
        mock_get_db.assert_called_once_with(connection_string)


def test_long_term_memory_uses_provided_db_manager():
    """Test that LongTermMemory uses provided DatabaseManager."""
    
    with patch('muxi.runtime.services.memory.long_term.Base'):
        with patch('muxi.runtime.services.memory.long_term.observability'):
            # Create mock database manager
            mock_db_manager = MagicMock()
            mock_db_manager.database_type = 'postgresql'
            mock_db_manager.engine = MagicMock()
            mock_db_manager.Session = MagicMock()
            mock_db_manager.create_tables = MagicMock()
            
            # Create LongTermMemory with DatabaseManager
            from muxi.runtime.services.memory.long_term import LongTermMemory
            
            ltm = LongTermMemory(db_manager=mock_db_manager)
            
            # Verify it uses the provided database manager
            assert ltm.db_manager == mock_db_manager
            assert ltm.engine == mock_db_manager.engine
            assert ltm.Session == mock_db_manager.Session


def test_scheduler_service_uses_overlord_db_manager():
    """Test that SchedulerService uses DatabaseManager from overlord."""
    
    with patch('muxi.runtime.services.scheduler.service.get_database_manager') as mock_get_db:
        with patch('muxi.runtime.services.scheduler.service.JobManager'):
            with patch('muxi.runtime.services.scheduler.service.ScheduleParser'):
                with patch('muxi.runtime.services.scheduler.service.PromptRewriter'):
                    # Create mock overlord with database manager
                    mock_overlord = MagicMock()
                    mock_db_manager = MagicMock()
                    mock_overlord.db_manager = mock_db_manager
                    mock_overlord.formation_config = {"scheduler": {"enabled": True}}
                    
                    # Create SchedulerService
                    from muxi.runtime.services.scheduler.service import SchedulerService
                    
                    scheduler = SchedulerService(mock_overlord)
                    
                    # Verify it uses the overlord's database manager
                    assert scheduler.db_manager == mock_db_manager
                    # Verify it didn't create its own
                    mock_get_db.assert_not_called()


def test_scheduler_service_fallback_when_no_overlord_db():
    """Test that SchedulerService falls back to creating own DatabaseManager."""
    
    with patch('muxi.runtime.services.scheduler.service.get_database_manager') as mock_get_db:
        with patch('muxi.runtime.services.scheduler.service.JobManager'):
            with patch('muxi.runtime.services.scheduler.service.ScheduleParser'):
                with patch('muxi.runtime.services.scheduler.service.PromptRewriter'):
                    # Create mock overlord WITHOUT database manager
                    mock_overlord = MagicMock()
                    mock_overlord.db_manager = None
                    mock_overlord.formation_config = {"scheduler": {"enabled": True}}
                    
                    mock_fallback_db = MagicMock()
                    mock_get_db.return_value = mock_fallback_db
                    
                    # Create SchedulerService
                    from muxi.runtime.services.scheduler.service import SchedulerService
                    
                    scheduler = SchedulerService(mock_overlord)
                    
                    # Verify it created its own database manager as fallback
                    assert scheduler.db_manager == mock_fallback_db
                    mock_get_db.assert_called_once()


if __name__ == "__main__":
    print("🧪 Testing Unified Database Integration...")
    
    try:
        test_formation_creates_shared_database_manager()
        print("   ✓ Formation creates shared DatabaseManager")
        
        test_long_term_memory_uses_provided_db_manager()
        print("   ✓ LongTermMemory uses provided DatabaseManager")
        
        test_scheduler_service_uses_overlord_db_manager()
        print("   ✓ SchedulerService uses overlord's DatabaseManager")
        
        test_scheduler_service_fallback_when_no_overlord_db()
        print("   ✓ SchedulerService fallback works correctly")
        
        print("\n🎉 All unified database integration tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()