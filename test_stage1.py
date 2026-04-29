#!/usr/bin/env python3
"""第一阶段（异常感知）功能测试脚本"""
from web_service_guard.agents.sentinel_agent import SentinelAgent

def test_sentinel_agent_basic():
    """测试Sentinel Agent基础功能：采集Traceback、生成修复任务"""
    print("=" * 60)
    print("开始测试第一阶段：异常感知与任务生成")
    print("=" * 60)
    
    # 初始化Sentinel Agent
    sentinel = SentinelAgent()
    print("Sentinel Agent 初始化成功")
    
    # 执行异常检测和任务生成
    tasks = sentinel.detect_and_create_tasks(
        service="test-web-service",
        repo="git@github.com:demo/test-service.git",
        branch="main"
    )
    
    print(f"\n采集到的修复任务数量：{len(tasks)}")
    
    if not tasks:
        print("未采集到任何任务，请检查日志路径和内容配置")
        return False
    
    # 验证任务结构
    for i, task in enumerate(tasks, 1):
        print(f"\n任务 {i} 详情：")
        print(f"  Run ID: {task.get('run_id')}")
        print(f"  关联仓库: {task.get('repo')}")
        print(f"  目标分支: {task.get('branch')}")
        print(f"  最大修复迭代次数: {task.get('max_iterations')}")
        
        bug_event = task.get('bug_event', {})
        print(f"  错误摘要: {bug_event.get('error_summary', 'N/A')}")
        print(f"  Traceback包含字符数: {len(task.get('traceback', ''))}")
        
        # 验证必填字段
        required_fields = ['run_id', 'bug_event', 'traceback', 'repo', 'branch', 'max_iterations']
        missing_fields = [field for field in required_fields if field not in task]
        
        if missing_fields:
            print(f"任务缺少必填字段: {missing_fields}")
            return False
        
        if 'traceback' in task and 'ZeroDivisionError' in task['traceback']:
            print("正确识别到ZeroDivisionError异常")
    
    print("\n第一阶段功能测试通过！Sentinel Agent可以正常采集异常并生成标准化修复任务")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_sentinel_agent_basic()
    exit(0 if success else 1)
