import os

import yaml
from dotenv import load_dotenv

# Load environment variables from .env when present.
load_dotenv()


class Config:
    def __init__(self):
        # Base settings
        self.log_path = os.getenv("LOG_PATH", "./app.log")

        # Model settings
        self.analyzer_model = os.getenv("ANALYZER_MODEL", "ep-20260423222752-9tcpw")
        self.analyzer_temperature = float(os.getenv("ANALYZER_TEMPERATURE", "0.3"))
        self.analyzer_max_tokens = int(os.getenv("ANALYZER_MAX_TOKENS", "1000"))
        self.analyzer_timeout = int(os.getenv("ANALYZER_TIMEOUT", "30"))

        # API settings
        self.doubao_api_url = os.getenv("DOUBAO_API_URL", "https://ark.cn-beijing.volces.com/api/v3")
        self.doubao_api_key = os.getenv("DOUBAO_API_KEY", "")
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")

        # Git settings
        self.git_repo_url = os.getenv("GIT_REPO_URL", "")
        self.github_token = os.getenv("GITHUB_TOKEN", "")
        self.git_branch_prefix = os.getenv("GIT_BRANCH_PREFIX", "fix-")
        self.git_commit_message = os.getenv("GIT_COMMIT_MESSAGE", "Auto-fix: {error_summary}")
        self.git_pr_title = os.getenv("GIT_PR_TITLE", "Auto-fix: {error_summary}")
        self.git_pr_body = os.getenv(
            "GIT_PR_BODY",
            "This is an automated fix for the error: {error_summary}",
        )

        # Feishu settings
        self.feishu_app_id = os.getenv("FEISHU_APP_ID", "")
        self.feishu_app_secret = os.getenv("FEISHU_APP_SECRET", "")
        self.feishu_webhook_url = os.getenv("FEISHU_WEBHOOK_URL", "")
        self.feishu_retry_count = int(os.getenv("FEISHU_RETRY_COUNT", "3"))
        self.feishu_retry_interval = int(os.getenv("FEISHU_RETRY_INTERVAL", "5"))

        # Monitoring settings
        self.monitor_log_pattern = os.getenv("MONITOR_LOG_PATTERN", "ERROR|Exception|Traceback")
        self.monitor_check_interval = int(os.getenv("MONITOR_CHECK_INTERVAL", "10"))
        self.monitor_max_log_size = int(os.getenv("MONITOR_MAX_LOG_SIZE", "1048576"))

        healthcheck_urls_raw = os.getenv("HEALTHCHECK_URLS", "[]")
        try:
            parsed_urls = yaml.safe_load(healthcheck_urls_raw) if healthcheck_urls_raw else []
        except yaml.YAMLError:
            parsed_urls = []
        self.healthcheck_urls = parsed_urls if isinstance(parsed_urls, list) else []
        self.healthcheck_timeout = int(os.getenv("HEALTHCHECK_TIMEOUT", "5"))

        # Code modification settings
        self.code_modifier_backup_enabled = os.getenv("CODE_MODIFIER_BACKUP_ENABLED", "True").lower() == "true"
        self.code_modifier_backup_dir = os.getenv("CODE_MODIFIER_BACKUP_DIR", "./backups")

        # Runtime settings
        self.max_iterations = int(os.getenv("MAX_ITERATIONS", "3"))
        self.tool_timeout_sec = int(os.getenv("TOOL_TIMEOUT_SEC", "60"))

        # Audit settings
        self.audit_storage_path = os.getenv("AUDIT_STORAGE_PATH", "./audit")

    def get(self, key, default=None):
        """Return a configuration value using dotted attribute lookup."""
        parts = key.split(".")
        value = self
        for part in parts:
            if hasattr(value, part):
                value = getattr(value, part)
            else:
                return default
        return value


# Shared config instance.
config = Config()
