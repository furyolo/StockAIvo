#!/usr/bin/env python3
"""
搜索功能测试运行脚本

运行所有搜索相关的测试用例，生成测试报告。
"""

import sys
import os
import subprocess
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_command(command, description):
    """运行命令并返回结果"""
    print(f"\n{'='*60}")
    print(f"运行: {description}")
    print(f"命令: {command}")
    print(f"{'='*60}")
    
    start_time = time.time()
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=project_root
        )
        end_time = time.time()
        
        print(f"执行时间: {end_time - start_time:.2f}秒")
        print(f"返回码: {result.returncode}")
        
        if result.stdout:
            print(f"\n标准输出:")
            print(result.stdout)
        
        if result.stderr:
            print(f"\n标准错误:")
            print(result.stderr)
        
        return result.returncode == 0, result
        
    except Exception as e:
        end_time = time.time()
        print(f"执行时间: {end_time - start_time:.2f}秒")
        print(f"执行失败: {e}")
        return False, None


def main():
    """主函数"""
    print("搜索功能测试套件")
    print(f"项目根目录: {project_root}")
    print(f"当前工作目录: {os.getcwd()}")
    
    # 测试命令列表
    test_commands = [
        {
            "command": "uv run python -m pytest tests/test_search_service.py -v",
            "description": "搜索服务单元测试",
            "required": True
        },
        {
            "command": "uv run python -m pytest tests/test_search_api.py -v",
            "description": "搜索API集成测试",
            "required": True
        },
        {
            "command": "uv run python -m pytest tests/test_search_performance.py -v -s",
            "description": "搜索性能测试",
            "required": False
        },
        {
            "command": "uv run python -m pytest tests/test_search_service.py tests/test_search_api.py --cov=stockaivo.search_service --cov=stockaivo.routers.search --cov-report=html --cov-report=term",
            "description": "代码覆盖率测试",
            "required": False
        }
    ]
    
    # 运行测试
    results = []
    total_tests = len(test_commands)
    passed_tests = 0
    
    for i, test_config in enumerate(test_commands, 1):
        print(f"\n\n[{i}/{total_tests}] 开始执行测试...")
        
        success, result = run_command(
            test_config["command"],
            test_config["description"]
        )
        
        results.append({
            "description": test_config["description"],
            "command": test_config["command"],
            "success": success,
            "required": test_config["required"],
            "result": result
        })
        
        if success:
            passed_tests += 1
            print(f"✅ {test_config['description']} - 通过")
        else:
            status = "❌ 失败" if test_config["required"] else "⚠️ 可选测试失败"
            print(f"{status} {test_config['description']}")
    
    # 生成测试报告
    print(f"\n\n{'='*80}")
    print("测试结果总结")
    print(f"{'='*80}")
    
    print(f"总测试数: {total_tests}")
    print(f"通过测试: {passed_tests}")
    print(f"失败测试: {total_tests - passed_tests}")
    
    print(f"\n详细结果:")
    for result in results:
        status_icon = "✅" if result["success"] else ("❌" if result["required"] else "⚠️")
        required_text = "(必需)" if result["required"] else "(可选)"
        print(f"  {status_icon} {result['description']} {required_text}")
    
    # 检查必需测试是否都通过
    required_failed = [r for r in results if r["required"] and not r["success"]]
    
    if required_failed:
        print(f"\n❌ 有 {len(required_failed)} 个必需测试失败:")
        for result in required_failed:
            print(f"  - {result['description']}")
        print("\n请修复失败的测试后再继续。")
        return False
    else:
        print(f"\n✅ 所有必需测试都已通过！")
        
        optional_failed = [r for r in results if not r["required"] and not r["success"]]
        if optional_failed:
            print(f"\n⚠️ 有 {len(optional_failed)} 个可选测试失败:")
            for result in optional_failed:
                print(f"  - {result['description']}")
            print("可选测试失败不影响核心功能。")
        
        return True


def run_specific_test(test_name):
    """运行特定测试"""
    test_files = {
        "service": "tests/test_search_service.py",
        "api": "tests/test_search_api.py",
        "performance": "tests/test_search_performance.py",
        "all": "tests/test_search_*.py"
    }
    
    if test_name not in test_files:
        print(f"未知的测试名称: {test_name}")
        print(f"可用的测试: {', '.join(test_files.keys())}")
        return False
    
    test_file = test_files[test_name]
    command = f"uv run python -m pytest {test_file} -v"
    
    success, result = run_command(command, f"运行 {test_name} 测试")
    return success


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 运行特定测试
        test_name = sys.argv[1]
        success = run_specific_test(test_name)
    else:
        # 运行所有测试
        success = main()
    
    sys.exit(0 if success else 1)
