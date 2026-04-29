class RuntimeState:
    """运行时状态"""
    
    def __init__(self):
        self.run_id = None
        self.current_iteration = 0
        self.max_iterations = 3
        self.current_stage = "START"
        self.last_result = None
        self.artifacts = {}
        self.errors = []
        self.start_time = None
        self.end_time = None
    
    def set_run_id(self, run_id):
        """设置运行ID"""
        self.run_id = run_id
    
    def set_max_iterations(self, max_iterations):
        """设置最大迭代次数"""
        self.max_iterations = max_iterations
    
    def increment_iteration(self):
        """增加迭代次数"""
        self.current_iteration += 1
    
    def set_current_stage(self, stage):
        """设置当前阶段"""
        self.current_stage = stage
    
    def set_last_result(self, result):
        """设置最后一次结果"""
        self.last_result = result
    
    def add_artifact(self, key, value):
        """添加产物"""
        self.artifacts[key] = value
    
    def add_error(self, error):
        """添加错误"""
        self.errors.append(error)
    
    def get_state(self):
        """获取当前状态"""
        return {
            "run_id": self.run_id,
            "current_iteration": self.current_iteration,
            "max_iterations": self.max_iterations,
            "current_stage": self.current_stage,
            "artifacts": self.artifacts,
            "errors": self.errors,
            "start_time": self.start_time,
            "end_time": self.end_time
        }
    
    def reset(self):
        """重置状态"""
        self.current_iteration = 0
        self.current_stage = "START"
        self.last_result = None
        self.artifacts = {}
        self.errors = []
        self.start_time = None
        self.end_time = None