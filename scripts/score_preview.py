#!/usr/bin/env python3
"""
Level114 Subnet - Score Preview CLI

Command-line tool for previewing server scores, analyzing performance,
and debugging the scoring system.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from collections import deque

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from level114.validator.scoring import (
        ServerReport, MinerContext, calculate_miner_score,
        evaluate_infrastructure, evaluate_participation, evaluate_reliability,
        verify_report_integrity, get_constants_summary,
        EXCELLENT_SCORE_THRESHOLD, GOOD_SCORE_THRESHOLD, POOR_SCORE_THRESHOLD,
        get_score_classification
    )
    from level114.validator.storage import ValidatorStorage
    from level114.api.collector_center_api import CollectorCenterAPI
except ImportError as e:
    print(f"Error importing Level114 modules: {e}")
    print("Make sure you're running from the project root directory")
    sys.exit(1)


class ScorePreview:
    """Score preview and analysis tool"""
    
    def __init__(self, api_key=None, collector_url=None, db_path=None):
        """Initialize the preview tool"""
        self.storage = ValidatorStorage(db_path) if db_path else None
        self.collector_api = None
        
        if api_key and collector_url:
            try:
                self.collector_api = CollectorCenterAPI(collector_url, api_key=api_key)
                print(f"✅ Connected to collector API: {collector_url}")
            except Exception as e:
                print(f"⚠️  Failed to connect to collector API: {e}")
    
    def preview_from_json(self, json_file: str, latency: float = 0.1):
        """Preview score from JSON file"""
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            # Handle both single report and collector response format
            if 'items' in data and isinstance(data['items'], list):
                # Collector response format
                if not data['items']:
                    print("❌ No reports found in collector response")
                    return
                report_data = data['items'][0]
            else:
                # Single report format
                report_data = data
            
            report = ServerReport.from_dict(report_data)
            self._analyze_single_report(report, latency)
            
        except Exception as e:
            print(f"❌ Error reading JSON file: {e}")
    
    def preview_from_api(self, server_id: str):
        """Preview score from collector API"""
        if not self.collector_api:
            print("❌ Collector API not configured")
            return
        
        try:
            # Get recent reports
            success, reports = self.collector_api.get_server_reports(server_id, limit=10)
            
            if not success:
                print(f"❌ Failed to fetch reports for server {server_id}")
                return
            
            if not reports:
                print(f"❌ No reports found for server {server_id}")
                return
            
            # Parse reports
            parsed_reports = []
            for report_data in reports:
                try:
                    report = ServerReport.from_dict(report_data)
                    parsed_reports.append(report)
                except Exception as e:
                    print(f"⚠️  Failed to parse report: {e}")
                    continue
            
            if not parsed_reports:
                print("❌ No valid reports found")
                return
            
            # Analyze latest report with history
            latest_report = parsed_reports[0]
            history = deque(reversed(parsed_reports), maxlen=60)
            
            print(f"📊 Analyzing server {server_id} with {len(history)} reports")
            self._analyze_with_history(latest_report, history)
            
        except Exception as e:
            print(f"❌ API error: {e}")
    
    def preview_from_storage(self, server_id: str):
        """Preview score from local storage"""
        if not self.storage:
            print("❌ Storage not configured")
            return
        
        try:
            # Get server stats
            stats = self.storage.get_server_stats(server_id)
            if not stats.get('total_reports', 0):
                print(f"❌ No reports found for server {server_id} in storage")
                return
            
            # Load recent history
            history = self.storage.load_history(server_id, max_rows=20)
            if not history:
                print(f"❌ No report history found for server {server_id}")
                return
            
            latest_report = history[-1]  # Most recent
            
            print(f"📊 Analyzing server {server_id} from storage")
            print(f"   Total reports: {stats['total_reports']}")
            print(f"   Average TPS: {stats['avg_tps']:.1f}")
            print(f"   Average latency: {stats['avg_latency']:.3f}s")
            print(f"   Compliance rate: {stats['compliance_rate']:.1%}")
            print()
            
            self._analyze_with_history(latest_report, history, stats['avg_latency'])
            
        except Exception as e:
            print(f"❌ Storage error: {e}")
    
    def _analyze_single_report(self, report: ServerReport, latency: float = 0.1):
        """Analyze a single report without history"""
        print(f"📋 Single Report Analysis")
        print(f"   Server ID: {report.server_id}")
        print(f"   Report ID: {report.id}")
        print(f"   Timestamp: {report.created_at}")
        print()
        
        self._print_report_details(report)
        
        # Create minimal context
        ctx = MinerContext(
            report=report,
            http_latency_s=latency,
            registration_ok=True,  # Assume registered
            compliance_ok=True,    # Assume compliant for preview
            history=deque([report], maxlen=60)
        )
        
        self._score_and_display(ctx, has_history=False)
    
    def _analyze_with_history(self, latest_report: ServerReport, history: deque, avg_latency: float = 0.1):
        """Analyze report with historical context"""
        print(f"📈 Historical Analysis")
        print(f"   History length: {len(history)} reports")
        print(f"   Time span: {self._calculate_time_span(history)}")
        print()
        
        self._print_report_details(latest_report)
        self._print_history_summary(history)
        
        # Create full context
        ctx = MinerContext(
            report=latest_report,
            http_latency_s=avg_latency,
            registration_ok=True,
            compliance_ok=True,
            history=history
        )
        
        self._score_and_display(ctx, has_history=True)
    
    def _print_report_details(self, report: ServerReport):
        """Print detailed report information"""
        payload = report.payload
        
        print("🖥️  Server Details:")
        print(f"   TPS: {payload.tps_actual:.1f} ({payload.tps_millis}ms)")
        print(f"   Players: {payload.player_count}/{payload.max_players} ({payload.player_ratio:.1%})")
        print(f"   Memory: {payload.memory_ram_info.usage_ratio:.1%} used ({payload.memory_ram_info.used_bytes/1e9:.1f}GB/{payload.memory_ram_info.total_bytes/1e9:.1f}GB)")
        print(f"   Uptime: {payload.system_info.uptime_days:.1f} days")
        print(f"   CPU: {payload.system_info.cpu_cores} cores / {payload.system_info.cpu_threads} threads")
        print(f"   Plugins: {len(payload.plugins)} ({', '.join(payload.plugins[:5])}{'...' if len(payload.plugins) > 5 else ''})")
        print(f"   Required plugins: {'✅' if payload.has_required_plugins else '❌'}")
        print()
    
    def _print_history_summary(self, history: deque):
        """Print summary of historical data"""
        if len(history) < 2:
            return
        
        tps_values = [r.payload.tps_actual for r in history]
        player_counts = [r.payload.player_count for r in history]
        uptimes = [r.payload.system_info.uptime_ms for r in history]
        
        print("📊 Historical Summary:")
        print(f"   TPS range: {min(tps_values):.1f} - {max(tps_values):.1f} (avg: {sum(tps_values)/len(tps_values):.1f})")
        print(f"   Player range: {min(player_counts)} - {max(player_counts)} (avg: {sum(player_counts)/len(player_counts):.1f})")
        
        # Check for uptime resets
        resets = sum(1 for i in range(1, len(uptimes)) if uptimes[i] < uptimes[i-1])
        if resets > 0:
            print(f"   ⚠️  Uptime resets detected: {resets}")
        else:
            print(f"   ✅ No uptime resets detected")
        
        print()
    
    def _calculate_time_span(self, history: deque) -> str:
        """Calculate time span of history"""
        if len(history) < 2:
            return "Single report"
        
        first_time = history[0].client_timestamp_ms
        last_time = history[-1].client_timestamp_ms
        span_hours = (last_time - first_time) / (1000 * 3600)
        
        if span_hours < 2:
            return f"{span_hours * 60:.0f} minutes"
        elif span_hours < 48:
            return f"{span_hours:.1f} hours"
        else:
            return f"{span_hours / 24:.1f} days"
    
    def _score_and_display(self, ctx: MinerContext, has_history: bool):
        """Calculate and display scores"""
        print("🎯 Scoring Analysis:")
        
        # Calculate component scores
        infra_score = evaluate_infrastructure(ctx)
        part_score = evaluate_participation(ctx)
        rely_score = evaluate_reliability(ctx)
        
        print(f"   Infrastructure: {infra_score:.3f} (40%)")
        print(f"     ├─ TPS: {ctx.report.payload.tps_actual:.1f}/{20.0} = {min(ctx.report.payload.tps_actual/20.0, 1.0):.3f}")
        print(f"     ├─ Latency: {ctx.http_latency_s:.3f}s = {max(0, 1 - ctx.http_latency_s):.3f}")
        print(f"     └─ Memory: {ctx.report.payload.memory_ram_info.free_ratio:.1%} free")
        
        print(f"   Participation: {part_score:.3f} (35%)")
        print(f"     ├─ Compliance: {'✅' if ctx.report.payload.has_required_plugins else '❌'}")
        print(f"     ├─ Players: {ctx.report.payload.player_count} active")
        print(f"     └─ Registration: {'✅' if ctx.registration_ok else '❌'}")
        
        print(f"   Reliability: {rely_score:.3f} (25%)")
        if has_history:
            print(f"     ├─ Uptime trend: Based on {len(ctx.history)} reports")
            print(f"     ├─ TPS stability: Coefficient of variation analysis")
            print(f"     └─ Recovery: Issue recovery time analysis")
        else:
            print(f"     └─ Basic uptime: {ctx.report.payload.system_info.uptime_days:.1f} days")
        
        # Calculate final score
        final_score, components = calculate_miner_score(ctx)
        classification = get_score_classification(final_score)
        
        print()
        print(f"🏆 Final Score: {final_score}/1000 ({classification.upper()})")
        
        # Show thresholds
        print(f"   Thresholds:")
        print(f"     Excellent: ≥{EXCELLENT_SCORE_THRESHOLD} {'✅' if final_score >= EXCELLENT_SCORE_THRESHOLD else '❌'}")
        print(f"     Good: ≥{GOOD_SCORE_THRESHOLD} {'✅' if final_score >= GOOD_SCORE_THRESHOLD else '❌'}")
        print(f"     Poor: <{POOR_SCORE_THRESHOLD} {'⚠️' if final_score < POOR_SCORE_THRESHOLD else '✅'}")
        
        # Improvement suggestions
        self._suggest_improvements(ctx, components)
    
    def _suggest_improvements(self, ctx: MinerContext, components: dict):
        """Suggest improvements based on scores"""
        suggestions = []
        
        if components['infrastructure'] < 0.7:
            if ctx.report.payload.tps_actual < 18:
                suggestions.append("🔧 Improve server TPS performance (optimize plugins, reduce lag)")
            if ctx.http_latency_s > 0.3:
                suggestions.append("🌐 Reduce network latency (better hosting, CDN)")
            if ctx.report.payload.memory_ram_info.free_ratio < 0.2:
                suggestions.append("💾 Increase available memory or optimize usage")
        
        if components['participation'] < 0.7:
            if not ctx.report.payload.has_required_plugins:
                suggestions.append("🔌 Install required plugins: Level114")
            if ctx.report.payload.player_count == 0:
                suggestions.append("👥 Attract players to increase activity score")
        
        if components['reliability'] < 0.7:
            if ctx.report.payload.system_info.uptime_hours < 48:
                suggestions.append("⏰ Improve server uptime and stability")
        
        if suggestions:
            print()
            print("💡 Improvement Suggestions:")
            for suggestion in suggestions:
                print(f"   {suggestion}")
    
    def show_constants(self):
        """Display scoring constants and configuration"""
        constants = get_constants_summary()
        
        print("⚙️  Scoring Configuration:")
        print()
        
        print("🎯 Performance Targets:")
        targets = constants['performance_targets']
        for key, value in targets.items():
            print(f"   {key.replace('_', ' ').title()}: {value}")
        
        print()
        print("⚖️  Scoring Weights:")
        weights = constants['weights']
        for component, weight in weights.items():
            print(f"   {component.title()}: {weight:.0%}")
        
        print()
        print("🔧 Sub-component Weights:")
        for category, sub_weights in constants['sub_weights'].items():
            print(f"   {category.title()}:")
            for sub_component, weight in sub_weights.items():
                print(f"     {sub_component.replace('_', ' ').title()}: {weight:.0%}")
        
        print()
        print("🏆 Score Thresholds:")
        thresholds = constants['score_range']['thresholds']
        for tier, threshold in thresholds.items():
            print(f"   {tier.title()}: {threshold}")
        
        print()
        print("🔌 Required Plugins:")
        for plugin in constants['required_plugins']:
            print(f"   • {plugin}")
        
        print()
        print("✨ Bonus Plugins:")
        for plugin in constants['bonus_plugins']:
            print(f"   • {plugin}")


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Level114 Subnet Score Preview Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview score from JSON file
  python score_preview.py --json report.json
  
  # Preview from collector API
  python score_preview.py --server-id dd227594-... --from-api
  
  # Preview from local storage
  python score_preview.py --server-id dd227594-... --from-storage
  
  # Show scoring configuration
  python score_preview.py --show-constants
        """
    )
    
    # Input source options
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument('--json', help='JSON file with server report')
    input_group.add_argument('--from-api', action='store_true', help='Fetch from collector API')
    input_group.add_argument('--from-storage', action='store_true', help='Load from local storage')
    input_group.add_argument('--show-constants', action='store_true', help='Show scoring constants')
    
    # Server identification
    parser.add_argument('--server-id', help='Server ID to analyze')
    
    # API configuration
    parser.add_argument('--api-key', help='Collector API key')
    parser.add_argument('--collector-url', default='http://collector.level114.io:3000', 
                       help='Collector API URL')
    
    # Analysis options
    parser.add_argument('--latency', type=float, default=0.1, 
                       help='HTTP latency in seconds (default: 0.1)')
    parser.add_argument('--db-path', help='Path to storage database')
    
    args = parser.parse_args()
    
    # Show constants and exit
    if args.show_constants:
        preview = ScorePreview()
        preview.show_constants()
        return
    
    # Validate arguments
    if args.from_api and not args.server_id:
        parser.error("--from-api requires --server-id")
    
    if args.from_storage and not args.server_id:
        parser.error("--from-storage requires --server-id")
    
    if args.from_api and not args.api_key:
        parser.error("--from-api requires --api-key")
    
    if not any([args.json, args.from_api, args.from_storage]):
        parser.error("Must specify one of: --json, --from-api, --from-storage")
    
    # Initialize preview tool
    try:
        preview = ScorePreview(
            api_key=args.api_key,
            collector_url=args.collector_url,
            db_path=args.db_path
        )
    except Exception as e:
        print(f"❌ Failed to initialize preview tool: {e}")
        sys.exit(1)
    
    # Execute analysis
    try:
        if args.json:
            preview.preview_from_json(args.json, args.latency)
        elif args.from_api:
            preview.preview_from_api(args.server_id)
        elif args.from_storage:
            preview.preview_from_storage(args.server_id)
            
    except KeyboardInterrupt:
        print("\n⏹️  Analysis interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
