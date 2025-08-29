#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Status Validation Test Runner Script
状态枚举验证测试执行脚本，支持集成测试+Postman集合联合验证

Created: 2025-01-18
Version: V2.3
Purpose: 一键执行状态枚举验证，生成详细报告
"""

import os
import sys
import subprocess
import json
import time
from pathlib import Path
from typing import Dict, Any, List


class StatusValidationRunner:
    """Status validation test runner with reporting."""
    
    def __init__(self, base_dir: str = None):
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent.parent
        self.project_root = self.base_dir.parent
        self.reports_dir = self.project_root / "reports" / "status_validation"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
        # Test configuration
        self.api_base_url = os.getenv('API_BASE_URL', 'http://localhost:8000')
        self.postman_collection = self.project_root / "tests" / "postman" / "status_enum_v2.3.postman_collection.json"
        self.postman_environment = self.project_root / "tests" / "postman" / "postman_environment_local.json"
        
    def run_integration_tests(self) -> Dict[str, Any]:
        """Run Python integration tests for status validation."""
        print("🔬 Running Status Validation Integration Tests...")
        
        # Set environment variables
        os.environ['API_BASE_URL'] = self.api_base_url
        
        # Run unittest with proper module path
        cmd = [
            sys.executable, "-m", "unittest", 
            "tests.integration.status_validation_test",
            "-v"
        ]
        
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                cwd=str(self.project_root),
                timeout=300  # 5 minutes timeout
            )
            
            duration = time.time() - start_time
            
            return {
                "type": "integration_tests",
                "success": result.returncode == 0,
                "duration": duration,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
            
        except subprocess.TimeoutExpired:
            return {
                "type": "integration_tests",
                "success": False,
                "duration": time.time() - start_time,
                "error": "Test execution timeout (5 minutes)",
                "returncode": -1
            }
        except Exception as e:
            return {
                "type": "integration_tests", 
                "success": False,
                "duration": time.time() - start_time,
                "error": str(e),
                "returncode": -1
            }
    
    def run_postman_collection(self) -> Dict[str, Any]:
        """Run Postman collection using Newman CLI."""
        print("📮 Running Postman Status Enum Collection...")
        
        if not self.postman_collection.exists():
            return {
                "type": "postman_collection",
                "success": False,
                "error": f"Postman collection not found: {self.postman_collection}",
                "returncode": -1
            }
        
        # Build newman command
        cmd = ["newman", "run", str(self.postman_collection)]
        
        if self.postman_environment.exists():
            cmd.extend(["-e", str(self.postman_environment)])
        
        # Add reporting options
        report_file = self.reports_dir / f"postman_report_{int(time.time())}.json"
        cmd.extend([
            "--reporters", "json,cli",
            "--reporter-json-export", str(report_file),
            "--timeout", "30000",  # 30 seconds per request
            "--delay-request", "500"  # 500ms delay between requests
        ])
        
        # Inject base URL aliases to handle mixed variable naming in collection
        for alias in ["baseUrl", "BASE_URL", "baseurl"]:
            cmd.extend(["--env-var", f"{alias}={self.api_base_url}"])
        
        start_time = time.time()
        try:
            # Set environment variables for proper encoding on Windows
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            env['NODE_OPTIONS'] = '--no-deprecation'  # Suppress deprecation warnings
            
            # Use shell=True with proper encoding handling
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                encoding='utf-8',  # Force UTF-8 encoding
                errors='replace',  # Replace invalid characters instead of failing
                timeout=600,  # 10 minutes timeout
                shell=True,  # Enable shell for PATH resolution on Windows
                env=env
            )
            
            duration = time.time() - start_time
            
            # Try to load detailed results from JSON report
            detailed_results = {}
            if report_file.exists():
                try:
                    with open(report_file, 'r', encoding='utf-8') as f:
                        detailed_results = json.load(f)
                except Exception as e:
                    detailed_results = {"json_parse_error": str(e)}

            # Inject effective environment used (base URL) for transparency
            effective_env = {
                "baseUrl": self.api_base_url
            }
            if self.postman_environment.exists():
                try:
                    with open(self.postman_environment, 'r', encoding='utf-8') as ef:
                        env_json = json.load(ef)
                        # Try detect baseUrl-like keys
                        kv = {v.get('key'): v.get('value') for v in env_json.get('values', [])}
                        for k in ["baseUrl", "BASE_URL", "baseurl"]:
                            if k in kv and kv[k]:
                                effective_env["baseUrl"] = kv[k]
                                break
                except Exception:
                    pass

            return {
                "type": "postman_collection",
                "success": result.returncode == 0,
                "duration": duration,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "report_file": str(report_file),
                "detailed_results": detailed_results,
                "effective_env": effective_env,
                "newman_detected": True
            }
            
        except subprocess.TimeoutExpired:
            return {
                "type": "postman_collection",
                "success": False,
                "duration": time.time() - start_time,
                "error": "Newman execution timeout (10 minutes)",
                "returncode": -1
            }
        except FileNotFoundError:
            # Attempt to locate newman via 'where' on Windows
            try:
                where_out = subprocess.check_output(["where", "newman"], text=True, shell=True, encoding='utf-8')
                return {
                    "type": "postman_collection",
                    "success": False,
                    "duration": 0,
                    "error": "Newman CLI not found in PATH for subprocess, but detected via 'where'. Try running again.",
                    "hint": where_out,
                    "returncode": -1,
                    "newman_detected": True
                }
            except Exception:
                return {
                    "type": "postman_collection",
                    "success": False,
                    "duration": 0,
                    "error": "Newman CLI not found. Install with: npm install -g newman",
                    "returncode": -1,
                    "newman_detected": False
                }
        except Exception as e:
            return {
                "type": "postman_collection",
                "success": False,
                "duration": time.time() - start_time,
                "error": str(e),
                "returncode": -1
            }
    
    def generate_combined_report(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate combined validation report."""
        print("📊 Generating Combined Validation Report...")
        
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        total_duration = 0
        
        integration_success = False
        postman_success = False
        
        for result in results:
            total_duration += result.get('duration', 0)
            
            if result['type'] == 'integration_tests':
                integration_success = result['success']
                # Parse test counts from stdout if available
                if result.get('stdout'):
                    lines = result['stdout'].split('\n')
                    for line in lines:
                        if 'Ran' in line and 'test' in line:
                            # Extract test count from "Ran X tests in Y.XXXs"
                            parts = line.split()
                            if len(parts) >= 2:
                                try:
                                    test_count = int(parts[1])
                                    total_tests += test_count
                                    if result['success']:
                                        passed_tests += test_count
                                    else:
                                        failed_tests += test_count
                                except ValueError:
                                    pass
            
            elif result['type'] == 'postman_collection':
                postman_success = result['success']
                # Parse Postman results from detailed_results
                detailed = result.get('detailed_results', {})
                if 'run' in detailed:
                    run_stats = detailed['run'].get('stats', {})
                    assertions = run_stats.get('assertions', {})
                    total_tests += assertions.get('total', 0)
                    passed_tests += assertions.get('passed', 0)
                    failed_tests += assertions.get('failed', 0)
        
        overall_success = integration_success and postman_success
        coverage_percentage = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "overall_success": overall_success,
            "total_duration": total_duration,
            "coverage_percentage": coverage_percentage,
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "integration_tests_success": integration_success,
                "postman_collection_success": postman_success
            },
            "detailed_results": results
        }
        
        # Save report
        report_file = self.reports_dir / f"combined_status_validation_{int(time.time())}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"📄 Report saved: {report_file}")
        return report
    
    def print_summary(self, report: Dict[str, Any]) -> None:
        """Print human-readable summary."""
        success_emoji = "✅" if report['overall_success'] else "❌"
        
        print(f"\n{success_emoji} Status Validation Summary:")
        print(f"   📊 Overall Success: {report['overall_success']}")
        print(f"   ⏱️  Total Duration: {report['total_duration']:.2f}s")
        print(f"   📈 Coverage: {report['coverage_percentage']:.1f}%")
        print(f"   🧪 Total Tests: {report['summary']['total_tests']}")
        print(f"   ✅ Passed: {report['summary']['passed_tests']}")
        print(f"   ❌ Failed: {report['summary']['failed_tests']}")
        print(f"   🔬 Integration Tests: {'✅' if report['summary']['integration_tests_success'] else '❌'}")
        print(f"   📮 Postman Collection: {'✅' if report['summary']['postman_collection_success'] else '❌'}")
        
        if not report['overall_success']:
            print(f"\n⚠️  Some tests failed. Check detailed logs for troubleshooting.")
        
        # Print specific failures
        for result in report['detailed_results']:
            if not result['success']:
                print(f"\n❌ {result['type']} failed:")
                if 'error' in result:
                    print(f"   Error: {result['error']}")
                if result.get('stderr'):
                    print(f"   Stderr: {result['stderr'][:200]}...")
    
    def run_all(self) -> bool:
        """Run all status validation tests and return overall success."""
        print("🚀 Starting Status Validation Test Suite...")
        print(f"   API Base URL: {self.api_base_url}")
        print(f"   Reports Directory: {self.reports_dir}")
        
        results = []
        
        # Run integration tests
        results.append(self.run_integration_tests())
        
        # Run Postman collection
        results.append(self.run_postman_collection())
        
        # Generate combined report
        report = self.generate_combined_report(results)
        
        # Print summary
        self.print_summary(report)
        
        return report['overall_success']


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run status validation tests")
    parser.add_argument("--api-url", default="http://localhost:8000", 
                       help="API base URL (default: http://localhost:8000)")
    parser.add_argument("--integration-only", action="store_true",
                       help="Run only integration tests")
    parser.add_argument("--postman-only", action="store_true", 
                       help="Run only Postman collection")
    
    args = parser.parse_args()
    
    # Set API URL from argument
    if args.api_url:
        os.environ['API_BASE_URL'] = args.api_url
    
    runner = StatusValidationRunner()
    
    if args.integration_only:
        result = runner.run_integration_tests()
        success = result['success']
        print(f"Integration tests: {'✅ PASSED' if success else '❌ FAILED'}")
        if not success:
            print(f"Error details: {result.get('error', result.get('stderr', 'Unknown error'))}")
    elif args.postman_only:
        result = runner.run_postman_collection() 
        success = result['success']
        print(f"Postman collection: {'✅ PASSED' if success else '❌ FAILED'}")
        if not success:
            print(f"Error details: {result.get('error', result.get('stderr', 'Unknown error'))}")
            # Extra diagnostics: show effective baseUrl and top failures parsed from report
            eff = result.get('effective_env', {})
            if eff:
                print(f"Effective baseUrl: {eff.get('baseUrl')}")
            detailed = result.get('detailed_results', {})
            failures = detailed.get('run', {}).get('failures', []) if isinstance(detailed, dict) else []
            if failures:
                print("Top failures:")
                for f in failures[:5]:
                    source = f.get('source', {})
                    name = source.get('name') if isinstance(source, dict) else str(source)
                    error = f.get('error', {})
                    message = error.get('message') if isinstance(error, dict) else str(error)
                    atype = f.get('at')
                    print(f" - [{atype}] {name}: {message}")
    else:
        success = runner.run_all()
    
    # Exit with appropriate code for CI/CD
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()