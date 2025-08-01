"""
Test thread-safe request counting.
"""

import threading
import time
from unittest.mock import Mock
from muxi.formation.server.server import FormationServer
from muxi.formation.formation import Formation


def test_thread_safe_request_counting():
    """Test that request counting is thread-safe."""
    
    # Create mock formation
    formation = Mock(spec=Formation)
    formation.config = {"server": {"host": "127.0.0.1", "port": 8000}}
    formation._api_keys = {"admin": "test", "client": "test"}
    formation.formation_id = "test-formation"
    
    # Create server
    server = FormationServer(formation)
    
    # Simulate concurrent requests
    num_threads = 100
    requests_per_thread = 100
    
    def increment_counter():
        for _ in range(requests_per_thread):
            with server._request_count_lock:
                server._request_count += 1
    
    # Start threads
    threads = []
    for _ in range(num_threads):
        t = threading.Thread(target=increment_counter)
        threads.append(t)
        t.start()
    
    # Wait for all threads
    for t in threads:
        t.join()
    
    # Verify count is correct
    expected = num_threads * requests_per_thread
    assert server._request_count == expected, f"Expected {expected}, got {server._request_count}"
    print(f"✅ Thread-safe counting works! Count: {server._request_count}")


def test_thread_safe_connections():
    """Test that active connections tracking is thread-safe."""
    
    # Create mock formation
    formation = Mock(spec=Formation)
    formation.config = {"server": {"host": "127.0.0.1", "port": 8000}}
    formation._api_keys = {"admin": "test", "client": "test"}
    formation.formation_id = "test-formation"
    
    # Create server
    server = FormationServer(formation)
    
    # Simulate concurrent connection adds/removes
    num_threads = 50
    
    def add_remove_connections():
        for i in range(100):
            conn = f"conn_{threading.current_thread().ident}_{i}"
            with server._active_connections_lock:
                server._active_connections.add(conn)
            # Simulate some work
            time.sleep(0.0001)
            with server._active_connections_lock:
                server._active_connections.discard(conn)
    
    # Start threads
    threads = []
    for _ in range(num_threads):
        t = threading.Thread(target=add_remove_connections)
        threads.append(t)
        t.start()
    
    # Wait for all threads
    for t in threads:
        t.join()
    
    # Verify no connections remain
    assert len(server._active_connections) == 0, f"Expected 0 connections, got {len(server._active_connections)}"
    print(f"✅ Thread-safe connection tracking works! Active connections: {len(server._active_connections)}")


if __name__ == "__main__":
    test_thread_safe_request_counting()
    test_thread_safe_connections()