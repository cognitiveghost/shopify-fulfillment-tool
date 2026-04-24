# Shared Modules for Shopify Tool and Packing Tool

This directory contains unified components that work identically in both the **Shopify Fulfillment Tool** and **Packing Tool**, ensuring consistency and reducing code duplication.

## Phase 1.4: Unified Statistics System

### Overview

The `StatsManager` provides a centralized statistics tracking system that:
- Works identically in both tools
- Stores data on the file server in `Stats/global_stats.json`
- Uses file locking for safe concurrent access from multiple PCs
- Tracks separate metrics for analysis (Shopify) and packing operations
- Provides per-client statistics breakdown

### Installation

Both repositories should have this `shared/` directory with identical content. You can:

1. **Option 1: Copy the directory** to both repositories
2. **Option 2: Use Git submodules** (recommended for keeping in sync)

```bash
# In shopify-fulfillment-tool repository
git submodule add <url-to-shared-repo> shared

# In packing-tool repository
git submodule add <url-to-shared-repo> shared
```

### File Structure

```
shared/
├── __init__.py           # Module initialization
├── stats_manager.py      # Unified StatsManager class
└── README.md            # This file
```

### Usage

#### In Shopify Tool

Record analysis completion:

```python
from shared import StatsManager

# Initialize (pass path to 0UFulfilment directory)
base_path = r"\\192.168.88.101\_Fulfilment_\0UFulfilment"
stats_manager = StatsManager(base_path)

# After completing analysis
stats_manager.record_analysis(
    client_id="M",
    session_id="2025-11-05_1",
    orders_count=150,
    metadata={
        "fulfillable_orders": 142,
        "courier_breakdown": {"DHL": 80, "DPD": 62}
    }
)
```

#### In Packing Tool

Record packing session completion:

```python
from shared import StatsManager

# Initialize
base_path = r"\\192.168.88.101\_Fulfilment_\0UFulfilment"
stats_manager = StatsManager(base_path)

# After completing packing session
stats_manager.record_packing(
    client_id="M",
    session_id="2025-11-05_1",
    worker_id="001",
    orders_count=142,
    items_count=450,
    metadata={
        "start_time": "2025-11-05T10:00:00",
        "end_time": "2025-11-05T12:30:00",
        "duration_seconds": 9000
    }
)
```

#### Retrieving Statistics

```python
# Get global statistics
global_stats = stats_manager.get_global_stats()
print(f"Total analyzed: {global_stats['total_orders_analyzed']}")
print(f"Total packed: {global_stats['total_orders_packed']}")
print(f"Total sessions: {global_stats['total_sessions']}")

# Get client-specific statistics
client_stats = stats_manager.get_client_stats("M")
print(f"Client M - Analyzed: {client_stats['orders_analyzed']}")
print(f"Client M - Packed: {client_stats['orders_packed']}")
print(f"Client M - Sessions: {client_stats['sessions']}")

# Get all clients
all_clients = stats_manager.get_all_clients_stats()
for client_id, stats in all_clients.items():
    print(f"{client_id}: {stats}")

# Get analysis history
analysis_history = stats_manager.get_analysis_history(
    client_id="M",
    limit=10
)

# Get packing history
packing_history = stats_manager.get_packing_history(
    client_id="M",
    worker_id="001",
    limit=10
)
```

### Data Structure

The `Stats/global_stats.json` file has the following structure:

```json
{
  "total_orders_analyzed": 5420,
  "total_orders_packed": 4890,
  "total_sessions": 312,
  "by_client": {
    "M": {
      "orders_analyzed": 2100,
      "orders_packed": 1950,
      "sessions": 145
    },
    "A": {
      "orders_analyzed": 1500,
      "orders_packed": 1420,
      "sessions": 98
    }
  },
  "analysis_history": [
    {
      "timestamp": "2025-11-05T14:30:00",
      "client_id": "M",
      "session_id": "2025-11-05_1",
      "orders_count": 150,
      "metadata": {
        "fulfillable_orders": 142,
        "courier_breakdown": {"DHL": 80, "DPD": 62}
      }
    }
  ],
  "packing_history": [
    {
      "timestamp": "2025-11-05T16:45:00",
      "client_id": "M",
      "session_id": "2025-11-05_1",
      "worker_id": "001",
      "orders_count": 142,
      "items_count": 450,
      "metadata": {
        "duration_seconds": 9000
      }
    }
  ],
  "last_updated": "2025-11-05T16:45:00",
  "version": "1.0"
}
```

### File Locking

The StatsManager implements robust file locking to handle concurrent access:

- **Windows**: Uses `msvcrt.locking()` for file locking
- **Unix/Linux**: Uses `fcntl.flock()` for file locking
- **Retry mechanism**: Automatically retries operations on lock conflicts
- **Timeout**: Configurable timeout for lock acquisition (default 5 seconds)

This ensures safe concurrent access from multiple:
- Workstations accessing the file server
- Threads within the same application
- Processes running simultaneously

### Error Handling

```python
from shared import StatsManager, StatsManagerError, FileLockError

try:
    stats_manager.record_analysis("M", "session1", 100)
except FileLockError as e:
    print(f"Could not acquire file lock: {e}")
except StatsManagerError as e:
    print(f"Statistics error: {e}")
```

### Configuration

The StatsManager accepts the following configuration options:

```python
stats_manager = StatsManager(
    base_path=r"\\server\path\0UFulfilment",
    max_retries=5,        # Number of retry attempts
    retry_delay=0.1       # Delay between retries (seconds)
)
```

### Testing

Run the test suite:

```bash
# Unit tests
pytest tests/test_unified_stats_manager.py -v

# Concurrent access tests
pytest tests/test_stats_concurrent_access.py -v

# All tests
pytest tests/test_unified_stats_manager.py tests/test_stats_concurrent_access.py -v
```

### Integration Example for Packing Tool

```python
# In src/packer_logic.py or wherever session completion is handled

from shared import StatsManager

class PackerLogic:
    def __init__(self, profile_manager, ...):
        self.profile_manager = profile_manager
        # Initialize unified stats manager
        base_path = profile_manager.get_base_path()
        self.unified_stats = StatsManager(base_path)

    def complete_session(self, client_id, session_id, worker_id):
        """Complete packing session and record statistics."""
        # ... existing logic to complete session ...

        # Get session metrics
        orders_completed = len(self.completed_orders)
        items_packed = sum(order['items_count'] for order in self.completed_orders)

        # Calculate duration
        duration_seconds = (self.end_time - self.start_time).total_seconds()

        # Record to unified stats
        self.unified_stats.record_packing(
            client_id=client_id,
            session_id=session_id,
            worker_id=worker_id,
            orders_count=orders_completed,
            items_count=items_packed,
            metadata={
                "start_time": self.start_time.isoformat(),
                "end_time": self.end_time.isoformat(),
                "duration_seconds": duration_seconds
            }
        )

        # ... rest of completion logic ...
```

### Integration Example for Shopify Tool

```python
# In shopify_tool/core.py or wherever analysis is completed

from shared import StatsManager

def run_full_analysis(client_id, session_id, ...):
    """Run analysis and record statistics."""
    # ... existing analysis logic ...

    # After analysis is complete
    base_path = config.get('file_server_path')
    stats_manager = StatsManager(base_path)

    stats_manager.record_analysis(
        client_id=client_id,
        session_id=session_id,
        orders_count=len(analyzed_orders),
        metadata={
            "fulfillable_orders": len(fulfillable_orders),
            "courier_breakdown": get_courier_breakdown(analyzed_orders),
            "analysis_duration_seconds": analysis_duration
        }
    )

    # ... rest of the code ...
```

### Best Practices

1. **Always use the same base_path** across both tools (the 0UFulfilment directory)
2. **Record statistics at completion** - after analysis or packing session is done
3. **Include relevant metadata** for better tracking and debugging
4. **Handle errors gracefully** - stats recording should not block the main workflow
5. **Use consistent client IDs** across both tools
6. **Use session IDs** that match the actual session folders

### Troubleshooting

#### File Lock Timeout Errors

If you see `FileLockError` frequently:
1. Check network connectivity to file server
2. Increase `max_retries` and `retry_delay`
3. Verify no processes are holding files open unnecessarily

#### Data Not Updating

If statistics don't update:
1. Verify `base_path` is correct and accessible
2. Check file permissions on Stats directory
3. Verify file server is mounted correctly
4. Check logs for errors

#### Corrupted Statistics File

If the statistics file becomes corrupted:
1. The manager will automatically reset to default state
2. Previous data will be lost
3. Consider implementing regular backups

### Version History

- **v1.0.0** (Phase 1.4) - Initial unified statistics system
  - Centralized storage on file server
  - File locking for concurrent access
  - Separate tracking for analysis and packing
  - Per-client statistics

### Support

For issues or questions:
1. Check the integration tests for usage examples
2. Review the inline documentation in `stats_manager.py`
3. Consult the Unified Development Plan (Phase 1.4)
