import unittest
import tempfile
import os
from web_service_guard.primitive_tools.read_code import ReadCode
from web_service_guard.primitive_tools.edit_code import EditCode

class TestPrimitiveTools(unittest.TestCase):
    """测试PrimitiveTool"""
    
    def setUp(self):
        self.read_code_tool = ReadCode()
        self.edit_code_tool = EditCode()
        
        # 创建临时测试文件
        self.test_file = tempfile.NamedTemporaryFile(suffix='.py', delete=False)
        self.test_file.write(b'def divide(a, b):\n    return a / b\n')
        self.test_file.close()
    
    def tearDown(self):
        # 清理临时文件
        if os.path.exists(self.test_file.name):
            os.unlink(self.test_file.name)
    
    def test_read_code(self):
        """测试读取代码工具"""
        test_input = {
            "file": self.test_file.name
        }
        
        result = self.read_code_tool.execute(
            run_id="test_run_1",
            iteration=1,
            input_data=test_input,
            constraints={"read_only": True}
        )
        
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertIn('content', result['output'])
    
    def test_edit_code(self):
        """测试修改代码工具"""
        test_input = {
            "file": self.test_file.name,
            "changes": 'def divide(a, b):\n    if b == 0:\n        return 0\n    return a / b\n'
        }
        
        result = self.edit_code_tool.execute(
            run_id="test_run_1",
            iteration=1,
            input_data=test_input,
            constraints={"read_only": False}
        )
        
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertTrue(result['output']['modified'])

if __name__ == '__main__':
    unittest.main()