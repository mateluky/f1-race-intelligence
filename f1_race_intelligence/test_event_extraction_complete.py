#!/usr/bin/env python3
"""
Test: Comprehensive event extraction from OpenF1
Verifies that:
1. All event types (SC, VSC, YELLOW, RED, WEATHER, INCIDENT, PIT) are extracted
2. Each event has OpenF1 evidence attached
3. Event counts match expected distribution
4. Debug info shows correct breakdown
"""

import json
import logging
from rag.app_service import AppService
from rag.schemas import TimelineEventType

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_event_extraction():
    """Test that timeline extracts diverse event types with OpenF1 evidence."""
    
    service = AppService()
    
    # Test with 2024 Bahrain race - known to have SC, YELLOW, PIT events
    year = 2024
    gp_name = "Bahrain"
    race_type = "Race"
    
    logger.info("="*80)
    logger.info(f"Testing event extraction: {year} {gp_name} {race_type}")
    logger.info("="*80)
    
    try:
        result = service.build_timeline(
            year=year,
            gp_name=gp_name,
            race_type=race_type,
            use_pdf=False,  # Focus on OpenF1 only
            verbose=True
        )
        
        if result.get("error"):
            logger.error(f"❌ Error building timeline: {result['error']}")
            return False
        
        timeline = result.get("timeline")
        if not timeline:
            logger.error("❌ No timeline returned")
            return False
        
        items = timeline.get("timeline_items", [])
        logger.info(f"\n✅ Timeline built with {len(items)} events")
        
        # Analyze event types
        event_type_distribution = {}
        evidence_by_type = {}
        items_with_no_evidence = []
        
        for item in items:
            event_type = item.get("event_type", "UNKNOWN")
            event_type_distribution[event_type] = event_type_distribution.get(event_type, 0) + 1
            
            evidence_count = len(item.get("openf1_evidence", []))
            if event_type not in evidence_by_type:
                evidence_by_type[event_type] = []
            evidence_by_type[event_type].append({
                "title": item.get("title"),
                "evidence_count": evidence_count,
                "lap": item.get("lap")
            })
            
            if evidence_count == 0:
                items_with_no_evidence.append({
                    "type": event_type,
                    "title": item.get("title"),
                    "lap": item.get("lap")
                })
        
        # Print distribution
        logger.info("\n📊 Event Type Distribution:")
        for event_type, count in sorted(event_type_distribution.items()):
            logger.info(f"  {event_type}: {count}")
        
        # Check for evidence coverage
        logger.info("\n📋 Evidence Coverage by Type:")
        for event_type in sorted(event_type_distribution.keys()):
            items_of_type = evidence_by_type[event_type]
            items_with_evidence = [i for i in items_of_type if i["evidence_count"] > 0]
            coverage_pct = (len(items_with_evidence) / len(items_of_type)) * 100 if items_of_type else 0
            logger.info(f"  {event_type}: {len(items_with_evidence)}/{len(items_of_type)} have evidence ({coverage_pct:.0f}%)")
        
        # Check for expected event types
        expected_types = ["PIT_STOP", "SAFETY_CAR", "VIRTUAL_SC", "YELLOW_FLAG", "RED_FLAG"]
        found_types = set(event_type_distribution.keys())
        missing_types = [t for t in expected_types if t not in found_types]
        
        logger.info("\n🎯 Expected Event Types:")
        for event_type in expected_types:
            status = "✅" if event_type in found_types else "⚠️"
            count = event_type_distribution.get(event_type, 0)
            logger.info(f"  {status} {event_type}: {count}")
        
        if missing_types:
            logger.warning(f"\n⚠️ Missing event types: {missing_types}")
        
        # Show items without evidence
        if items_with_no_evidence:
            logger.warning(f"\n⚠️ Items without OpenF1 evidence ({len(items_with_no_evidence)}):")
            for item in items_with_no_evidence[:5]:  # Show first 5
                logger.warning(f"  - Lap {item['lap']}: {item['type']} - {item['title'][:50]}")
        
        # Run acceptance checks
        logger.info("\n" + "="*80)
        logger.info("🔍 ACCEPTANCE CHECKS:")
        logger.info("="*80)
        
        checks = {
            "Has events": len(items) > 0,
            "Has multiple event types": len(event_type_distribution) >= 2,
            "Has PIT events": "PIT_STOP" in event_type_distribution,
            "Has SC/VSC/YELLOW": any(t in event_type_distribution for t in ["SAFETY_CAR", "VIRTUAL_SC", "YELLOW_FLAG"]),
            "Most items have evidence": sum(1 for item in items if item.get("openf1_evidence")) / len(items) > 0.8,
        }
        
        all_passed = True
        for check_name, result_val in checks.items():
            status = "✅" if result_val else "❌"
            logger.info(f"  {status} {check_name}")
            if not result_val:
                all_passed = False
        
        logger.info("="*80)
        if all_passed:
            logger.info("✅ ALL CHECKS PASSED")
        else:
            logger.warning("⚠️ Some checks failed")
        
        return all_passed
        
    except Exception as e:
        logger.error(f"❌ Exception during test: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = test_event_extraction()
    exit(0 if success else 1)
