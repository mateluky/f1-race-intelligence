#!/usr/bin/env python3
"""Test OpenF1 evidence debugging and fixing.

Tests:
1. AppService logs OpenF1 client type
2. Timeline builder captures session resolution debug info
3. OpenF1 evidence is preserved during merge
4. Evidence counts appear in timeline
"""

import json
import logging
from rag.app_service import AppService
from rag.schemas import TimelineEventType

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

def test_appservice_init():
    """Test 1: AppService logs OpenF1 client type."""
    logger.info("=" * 70)
    logger.info("TEST 1: AppService init - OpenF1 client type logging")
    logger.info("=" * 70)
    
    # Test with mock
    app_mock = AppService(use_mock=True)
    assert hasattr(app_mock, 'openf1_client_type'), "AppService should have openf1_client_type"
    assert app_mock.openf1_client_type == "MockOpenF1Client", f"Expected MockOpenF1Client, got {app_mock.openf1_client_type}"
    logger.info(f"✓ Mock mode: {app_mock.openf1_client_type}")
    
    # Test with real (will be RealOpenF1Client or OpenF1Client)
    app_real = AppService(use_mock=False)
    assert hasattr(app_real, 'openf1_client_type'), "AppService should have openf1_client_type"
    logger.info(f"✓ Real mode: {app_real.openf1_client_type}")
    
    logger.info("✓ TEST 1 PASSED: Client type logging works\n")


def test_session_resolution_debug():
    """Test 2: Session resolution debug info is captured."""
    logger.info("=" * 70)
    logger.info("TEST 2: Session resolution debug info capture")
    logger.info("=" * 70)
    
    app = AppService(use_mock=True)
    
    # Simulate timeline building
    result = app.build_timeline(
        doc_id="test_australia_2025",
        year=2025,
        gp_name="Australian Grand Prix",
        session_type="RACE",
        auto_extract_metadata=False,
    )
    
    assert result["success"], f"Timeline build should succeed: {result}"
    
    # Check debug info
    debug_info = result.get("debug_info")
    assert debug_info is not None, "Should have debug_info in result"
    
    logger.info(f"Debug info keys: {list(debug_info.keys())}")
    
    # Verify session resolution
    assert "session_found" in debug_info, "Should have session_found flag"
    assert "detected_year" in debug_info, "Should have detected_year"
    assert "detected_gp" in debug_info, "Should have detected_gp"
    
    if debug_info.get("session_found"):
        assert "session_id" in debug_info, "Should have session_id if session found"
        logger.info(f"✓ Session found: {debug_info['session_id']}")
        logger.info(f"  - GP: {debug_info.get('matched_session', {}).get('gp_name')}")
        logger.info(f"  - Year: {debug_info.get('matched_session', {}).get('year')}")
        logger.info(f"  - Type: {debug_info.get('matched_session', {}).get('type')}")
    else:
        logger.warning(f"✗ Session NOT found: {debug_info.get('error')}")
    
    logger.info("✓ TEST 2 PASSED: Session resolution debug info captured\n")


def test_openf1_evidence_preservation():
    """Test 3: OpenF1 evidence is preserved during merge."""
    logger.info("=" * 70)
    logger.info("TEST 3: OpenF1 evidence preservation during merge")
    logger.info("=" * 70)
    
    app = AppService(use_mock=True)
    
    # Build timeline
    result = app.build_timeline(
        doc_id="test_australia_2025",
        year=2025,
        gp_name="Australian Grand Prix",
        session_type="RACE",
        auto_extract_metadata=False,
    )
    
    assert result["success"], f"Timeline build should succeed: {result}"
    
    timeline = result.get("timeline", {})
    items = timeline.get("timeline_items", [])
    
    logger.info(f"Timeline has {len(items)} items")
    
    if items:
        # Check that OpenF1 events have evidence
        openf1_evidence_count = 0
        for i, item in enumerate(items):
            evidence = item.get("openf1_evidence", [])
            if evidence:
                openf1_evidence_count += 1
                logger.info(f"  Item {i} ({item.get('event_type')}): {len(evidence)} OpenF1 evidence")
        
        logger.info(f"✓ {openf1_evidence_count} items have OpenF1 evidence")
        assert openf1_evidence_count > 0, "At least some items should have OpenF1 evidence"
    else:
        logger.warning("Timeline is empty - no items to check")
    
    logger.info("✓ TEST 3 PASSED: Evidence preservation works\n")


def test_evidence_in_table():
    """Test 4: Evidence counts appear correctly in table display."""
    logger.info("=" * 70)
    logger.info("TEST 4: Evidence counts in table display")
    logger.info("=" * 70)
    
    app = AppService(use_mock=True)
    
    # Build timeline
    result = app.build_timeline(
        doc_id="test_australia_2025",
        year=2025,
        gp_name="Australian Grand Prix",
        session_type="RACE",
        auto_extract_metadata=False,
    )
    
    assert result["success"], f"Timeline build should succeed: {result}"
    
    timeline = result.get("timeline", {})
    items = timeline.get("timeline_items", [])
    
    if items:
        logger.info("Evidence Summary:")
        for i, item in enumerate(items[:3]):  # Show first 3 items
            pdf_cites = item.get("pdf_citations", [])
            openf1_evid = item.get("openf1_evidence", [])
            
            evidence_str = f"PDF:{len(pdf_cites)}"
            if openf1_evid:
                evidence_str += f" | OpenF1:{len(openf1_evid)}"
            
            logger.info(f"  [{i}] {item.get('event_type')} - {evidence_str}")
        
        # Verify that not all are showing OpenF1:0
        has_openf1_evidence = any(
            len(item.get("openf1_evidence", [])) > 0 
            for item in items
        )
        
        logger.info(f"✓ Has OpenF1 evidence: {has_openf1_evidence}")
        assert has_openf1_evidence, "At least some items should have OpenF1 evidence > 0"
    
    logger.info("✓ TEST 4 PASSED: Evidence appears in timeline\n")


def test_client_type_in_result():
    """Test 5: Client type exposed in build_timeline result."""
    logger.info("=" * 70)
    logger.info("TEST 5: Client type in result dict")
    logger.info("=" * 70)
    
    app = AppService(use_mock=False)  # Real client
    
    result = app.build_timeline(
        doc_id="test_australia_2025",
        year=2025,
        gp_name="Australian Grand Prix",
        session_type="RACE",
        auto_extract_metadata=False,
    )
    
    client_type = result.get("openf1_client_type")
    logger.info(f"OpenF1 client type in result: {client_type}")
    
    assert client_type is not None, "Result should have openf1_client_type"
    assert client_type != "MockOpenF1Client" or app.use_mock, "Should be real client when use_mock=False"
    
    logger.info("✓ TEST 5 PASSED: Client type exposed in result\n")


if __name__ == "__main__":
    logger.info("\n" + "=" * 70)
    logger.info("OPENF1 EVIDENCE DEBUGGING - COMPREHENSIVE TEST")
    logger.info("=" * 70 + "\n")
    
    try:
        test_appservice_init()
        test_session_resolution_debug()
        test_openf1_evidence_preservation()
        test_evidence_in_table()
        test_client_type_in_result()
        
        logger.info("=" * 70)
        logger.info("✓✓✓ ALL TESTS PASSED ✓✓✓")
        logger.info("=" * 70)
        logger.info("\nSummary:")
        logger.info("1. ✓ AppService logs client type (Mock vs Real)")
        logger.info("2. ✓ Session resolution debug info captured")
        logger.info("3. ✓ OpenF1 evidence preserved during merge")
        logger.info("4. ✓ Evidence counts appear in table (not always 0)")
        logger.info("5. ✓ Client type exposed in result dict")
        
    except AssertionError as e:
        logger.error(f"\n❌ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"\n❌ UNEXPECTED ERROR: {e}", exc_info=True)
        exit(1)
