
import json
import os
import subprocess
import logging

logger = logging.getLogger(__name__)

class MosdacManager:
    def __init__(self, working_dir):
        self.working_dir = working_dir
        self.config_path = os.path.join(working_dir, "config.json")
        
    def create_config(self, username, password, dataset_id, start_date, end_date, bounding_box=None):
        """Generates the config.json file required by mdapi.py"""
        
        config = {
            "user_credentials": {
                "username/email": username,
                "password": password
            },
            "search_parameters": {
                "datasetId": dataset_id,
                "startTime": start_date,
                "endTime": end_date,
                "count": "100",
                "boundingBox": bounding_box or "",
                "gId": ""
            },
            "download_settings": {
                "download_path": os.path.join(self.working_dir, "downloads"),
                "organize_by_date": True,
                "skip_user_input": True,
                "generate_error_logs": True
            }
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)
            
        logger.info(f"MOSDAC Config generated at {self.config_path}")
        return self.config_path

    def run_downloader(self):
        """Executes the mdapi.py script"""
        mdapi_path = os.path.join(self.working_dir, "mdapi.py")
        
        if not os.path.exists(mdapi_path):
            return {"status": "error", "message": "mdapi.py not found in working directory. Please upload the script."}
            
        try:
            # Run the script and capture output
            # skip_user_prompt=True in config means we don't need to interact
            result = subprocess.run(
                ["python3", "mdapi.py"], 
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=300 # 5 min timeout
            )
            
            if result.returncode == 0:
                return {"status": "success", "output": result.stdout}
            else:
                return {"status": "failed", "error": result.stderr, "output": result.stdout}
                
        except Exception as e:
            return {"status": "error", "message": str(e)}

# Singleton instance for the app to use
# We can point this to a specific folder where the user drops mdapi.py
MOSDAC_WORK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mosdac_engine")
if not os.path.exists(MOSDAC_WORK_DIR):
    os.makedirs(MOSDAC_WORK_DIR)
    
mosdac_manager = MosdacManager(MOSDAC_WORK_DIR)
