import unittest
from unittest.mock import Mock, patch
from web_service_guard.agents.sentinel_agent import SentinelAgent
from web_service_guard.schemas.event import BugEvent

class TestSentinelAgent(unittest.TestCase):
    """测试第一阶段哨兵Agent功能"""
    
    def setUp(self):
        self.sentinel_agent = SentinelAgent()
        self.test_service = "test-web-service"
        self.test_repo = "git@github.com:user/test-service.git"
        self.test_branch = "main"
        
        # 模拟Traceback数据
        self.test_traceback = """
Traceback (most recent call last):
  File "/app/service.py", line 123, in handle_request
    result = divide(10, 0)
  File "/app/utils.py", line 45, in divide
    return a / b
ZeroDivisionError: division by zero
        """.strip()

    def test_detect_and_create_tasks_success(self):
        """测试正常场景下生成修复任务"""
        # Mock依赖的收集器和检测器
        with patch.object(self.sentinel_agent.traceback_collector, 'collect_tracebacks') as mock_collect:
            mock_collect.return_value = [self.test_traceback]
            
            with patch.object(self.sentinel_agent.event_detector, 'detect_events') as mock_detect:
                mock_event = Mock(spec=BugEvent)
                mock_event.timestamp = 1714000000
                mock_event.traceback = self.test_traceback
                mock_event.to_dict.return_value = {
                    "service": self.test_service,
                    "error_summary": "ZeroDivisionError: division by zero",
                    "traceback": self.test_traceback,
                    "timestamp": 1714000000
                }
                mock_detect.return_value = [mock_event]
                
                # 执行测试
                tasks = self.sentinel_agent.detect_and_create_tasks(
                    service=self.test_service,
                    repo=self.test_repo,
                    branch=self.test_branch
                )
                
                # 验证结果
                self.assertEqual(len(tasks), 1)
                task = tasks[0]
                self.assertEqual(task['run_id'], "repair_1714000000")
                self.assertEqual(task['repo'], self.test_repo)
                self.assertEqual(task['branch'], self.test_branch)
                self.assertEqual(task['max_iterations'], 3)
                self.assertIn('bug_event', task)
                self.assertIn('traceback', task)
                self.assertEqual(task['traceback'], self.test_traceback)

    def test_no_traceback_return_empty_tasks(self):
        """测试没有Traceback时返回空任务列表"""
        with patch.object(self.sentinel_agent.traceback_collector, 'collect_tracebacks') as mock_collect:
            mock_collect.return_value = []
            
            with patch.object(self.sentinel_agent.event_detector, 'detect_events') as mock_detect:
                mock_detect.return_value = []
                
                tasks = self.sentinel_agent.detect_and_create_tasks(
                    service=self.test_service,
                    repo=self.test_repo,
                    branch=self.test_branch
                )
                
                self.assertEqual(len(tasks), 0)

if __name__ == '__main__':
    unittest.main()
