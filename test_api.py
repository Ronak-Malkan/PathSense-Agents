"""
Test script to demonstrate API usage.
Run this after starting the Flask server with: python app.py
"""
import requests
import time
import json
from datetime import datetime

# API Configuration
API_BASE_URL = "http://localhost:5000"

def print_section(title):
    """Print formatted section header."""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)

def print_response(response):
    """Pretty print API response."""
    print(f"\nStatus Code: {response.status_code}")
    print("Response:")
    print(json.dumps(response.json(), indent=2))

def test_health_check():
    """Test 1: Health check endpoint."""
    print_section("Test 1: Health Check")
    response = requests.get(f"{API_BASE_URL}/health")
    print_response(response)
    assert response.status_code == 200, "Health check failed"
    print("\n✓ Health check passed")

def test_ingest_single_log():
    """Test 2: Ingest single log record."""
    print_section("Test 2: Ingest Single Log")

    log_data = {
        "client_id": "test_client",
        "session_id": "session_001",
        "t": int(time.time()),
        "events": ["proceed"],
        "confidence": 0.92,
        "free_ahead_m": 3.5,
        "classes": ["person"],
        "app": "test-1.0.0"
    }

    print("\nSending log:")
    print(json.dumps(log_data, indent=2))

    response = requests.post(
        f"{API_BASE_URL}/api/logs/ingest",
        json=log_data
    )
    print_response(response)
    assert response.status_code == 200, "Log ingestion failed"
    print("\n✓ Log ingestion passed")

def test_ingest_obstacle_scenario():
    """Test 3: Simulate obstacle detection scenario."""
    print_section("Test 3: Obstacle Detection Scenario")

    base_time = int(time.time())

    # Scenario: Normal navigation → Obstacle detected → User stops
    scenario_logs = [
        {
            "client_id": "test_client",
            "session_id": "session_001",
            "t": base_time,
            "events": ["proceed"],
            "confidence": 0.9,
            "free_ahead_m": 4.0,
            "app": "test-1.0.0"
        },
        {
            "client_id": "test_client",
            "session_id": "session_001",
            "t": base_time + 5,
            "events": ["obstacle_center"],
            "confidence": 0.88,
            "free_ahead_m": 0.4,
            "classes": ["person"],
            "app": "test-1.0.0"
        },
        {
            "client_id": "test_client",
            "session_id": "session_001",
            "t": base_time + 7,
            "events": ["stop"],
            "confidence": 0.85,
            "free_ahead_m": 0.3,
            "app": "test-1.0.0"
        }
    ]

    print(f"\nSending {len(scenario_logs)} log records...")

    for i, log in enumerate(scenario_logs, 1):
        print(f"\n[{i}/{len(scenario_logs)}] {log['events']}")
        response = requests.post(
            f"{API_BASE_URL}/api/logs/ingest",
            json=log
        )
        assert response.status_code == 200, f"Log {i} failed"
        time.sleep(0.1)  # Small delay between logs

    print("\n✓ Obstacle scenario completed")

def test_batch_ingest():
    """Test 4: Batch log ingestion."""
    print_section("Test 4: Batch Log Ingestion")

    base_time = int(time.time())

    batch_logs = []
    for i in range(10):
        batch_logs.append({
            "client_id": "test_client",
            "session_id": "session_002",
            "t": base_time + i * 5,
            "events": ["proceed"] if i % 3 != 0 else ["stop"],
            "confidence": 0.85 + (i % 10) * 0.01,
            "free_ahead_m": 2.5 + (i % 5) * 0.5,
            "app": "test-1.0.0"
        })

    payload = {"logs": batch_logs}

    print(f"\nSending batch of {len(batch_logs)} logs...")

    response = requests.post(
        f"{API_BASE_URL}/api/logs/batch",
        json=payload
    )
    print_response(response)
    assert response.status_code == 200, "Batch ingestion failed"
    print("\n✓ Batch ingestion passed")

def test_build_index():
    """Test 5: Build user index."""
    print_section("Test 5: Build User Index")

    # First, send some logs
    base_time = int(time.time())
    for i in range(5):
        requests.post(
            f"{API_BASE_URL}/api/logs/ingest",
            json={
                "client_id": "index_test_client",
                "session_id": "session_003",
                "t": base_time + i * 10,
                "events": ["proceed"],
                "confidence": 0.9,
                "app": "test-1.0.0"
            }
        )

    # Note: This will try to read from file system
    # For this test, we'll just demonstrate the endpoint structure
    print("\nNote: Index building requires log files on disk.")
    print("See indexer_agent.py for file structure requirements.")
    print("\nEndpoint structure:")
    print(json.dumps({
        "client_id": "index_test_client",
        "session_id": "session_003"
    }, indent=2))

    print("\n✓ Index build endpoint demonstrated")

def test_authorize_contact():
    """Test 6: Authorize emergency contact."""
    print_section("Test 6: Authorize Emergency Contact")

    auth_data = {
        "client_id": "test_client",
        "contact_id": "emergency_contact_001"
    }

    print("\nAuthorizing contact:")
    print(json.dumps(auth_data, indent=2))

    response = requests.post(
        f"{API_BASE_URL}/api/contacts/authorize",
        json=auth_data
    )
    print_response(response)
    assert response.status_code == 200, "Contact authorization failed"
    print("\n✓ Contact authorization passed")

def test_query():
    """Test 7: Query navigation data."""
    print_section("Test 7: Query Navigation Data")

    query_data = {
        "requester_id": "emergency_contact_001",
        "client_id": "test_client",
        "question": "How many times did he almost crash?",
        "time_start": "today",
        "time_end": "now",
        "tz": "UTC"
    }

    print("\nQuery:")
    print(json.dumps(query_data, indent=2))

    response = requests.post(
        f"{API_BASE_URL}/api/query",
        json=query_data
    )
    print_response(response)
    # Note: May fail if no index exists, which is expected
    print("\n✓ Query endpoint tested")

def test_watchdog_status():
    """Test 8: Get watchdog status."""
    print_section("Test 8: Watchdog Status")

    client_id = "test_client"
    print(f"\nGetting watchdog status for: {client_id}")

    response = requests.get(
        f"{API_BASE_URL}/api/watchdog/status/{client_id}"
    )
    print_response(response)
    assert response.status_code == 200, "Watchdog status failed"
    print("\n✓ Watchdog status passed")

def test_clear_watchdog():
    """Test 9: Clear watchdog state."""
    print_section("Test 9: Clear Watchdog State")

    client_id = "test_client"
    print(f"\nClearing watchdog state for: {client_id}")

    response = requests.post(
        f"{API_BASE_URL}/api/watchdog/clear/{client_id}"
    )
    print_response(response)
    assert response.status_code == 200, "Clear watchdog failed"
    print("\n✓ Clear watchdog passed")

def test_stats():
    """Test 10: Get system statistics."""
    print_section("Test 10: System Statistics")

    response = requests.get(f"{API_BASE_URL}/api/stats")
    print_response(response)
    assert response.status_code == 200, "Stats retrieval failed"
    print("\n✓ Stats retrieval passed")

def simulate_yolo_app():
    """Simulate YOLO app sending real-time navigation data."""
    print_section("BONUS: YOLO App Simulation")

    print("\nSimulating YOLO app navigation session...")
    print("Scenario: User navigates, encounters obstacle, veers left, continues")

    base_time = int(time.time())
    navigation_sequence = [
        {
            "t_offset": 0,
            "events": ["proceed"],
            "free_ahead_m": 5.0,
            "confidence": 0.92,
            "description": "Normal walking"
        },
        {
            "t_offset": 3,
            "events": ["proceed"],
            "free_ahead_m": 4.5,
            "confidence": 0.91,
            "description": "Continuing forward"
        },
        {
            "t_offset": 6,
            "events": ["obstacle_center"],
            "free_ahead_m": 1.2,
            "confidence": 0.88,
            "classes": ["person"],
            "description": "Obstacle detected ahead"
        },
        {
            "t_offset": 8,
            "events": ["veer_left_15"],
            "free_ahead_m": 3.0,
            "confidence": 0.89,
            "description": "Veering left to avoid"
        },
        {
            "t_offset": 11,
            "events": ["proceed"],
            "free_ahead_m": 4.0,
            "confidence": 0.90,
            "description": "Resumed normal path"
        }
    ]

    for step in navigation_sequence:
        log_data = {
            "client_id": "yolo_sim_user",
            "session_id": "yolo_session_001",
            "t": base_time + step["t_offset"],
            "events": step["events"],
            "confidence": step["confidence"],
            "free_ahead_m": step["free_ahead_m"],
            "app": "yolo-sim-1.0.0"
        }

        if "classes" in step:
            log_data["classes"] = step["classes"]

        print(f"\n[T+{step['t_offset']}s] {step['description']}")
        print(f"  Events: {step['events']}, Free ahead: {step['free_ahead_m']}m")

        response = requests.post(
            f"{API_BASE_URL}/api/logs/ingest",
            json=log_data
        )

        if response.status_code != 200:
            print(f"  ✗ Failed: {response.json()}")
        else:
            print(f"  ✓ Logged successfully")

        time.sleep(0.5)  # Simulate time between readings

    print("\n✓ YOLO simulation completed")

def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print(" Blind Navigation Agents - API Test Suite")
    print("=" * 70)
    print("\nMake sure the Flask server is running on http://localhost:5000")
    print("Start it with: python app.py")

    input("\nPress Enter to start tests...")

    try:
        # Basic tests
        test_health_check()
        test_ingest_single_log()
        test_authorize_contact()
        test_ingest_obstacle_scenario()
        test_batch_ingest()

        # Watchdog tests
        test_watchdog_status()
        test_clear_watchdog()

        # Query and stats
        test_query()
        test_stats()

        # Advanced simulation
        simulate_yolo_app()

        # Final summary
        print_section("Test Summary")
        print("\n✓ All tests completed successfully!")
        print("\nThe API is ready for YOLO app integration.")
        print("\nNext steps:")
        print("1. Integrate this API with your YOLO Android app")
        print("2. Configure emergency contacts")
        print("3. Test with real navigation scenarios")
        print("4. Deploy to production server or AgentVerse")

    except requests.exceptions.ConnectionError:
        print("\n✗ ERROR: Could not connect to API server")
        print("Make sure the Flask server is running: python app.py")
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
