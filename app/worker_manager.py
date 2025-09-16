# app/worker_manager.py
import subprocess
import sys
import os
import threading
import time
import structlog
from pathlib import Path
from celery.app.control import Control
from app.background.tasks import celery_app

log = structlog.get_logger()

class CeleryWorkerManager:
    def __init__(self):
        self.worker_process = None
        self.worker_thread = None
        self.control = Control(celery_app)
        self.last_health_check = 0
        self.health_check_interval = 5  # seconds
        
    def start_worker(self, concurrency=4):
        """Start Celery worker in a background thread"""
        if self.worker_thread and self.worker_thread.is_alive():
            if self.is_healthy():
                log.info("celery.worker.already_running")
                return
            else:
                log.warning("celery.worker.unhealthy.restarting")
                self.stop_worker()
                
        def run_worker():
            try:
                log.info("celery.worker.starting", concurrency=concurrency)
                
                # Use python -m celery to ensure it works across environments
                cmd = [
                    sys.executable, "-m", "celery", 
                    "-A", "app.worker", "worker", 
                    "--loglevel=info", 
                    f"--concurrency={concurrency}",
                    "--pool=threads",  # Use threads instead of processes for Windows compatibility
                    "--without-heartbeat",  # Disable heartbeat for Windows
                    "--without-gossip",  # Disable gossip for single worker
                ]
                
                # Ensure CELERY_BROKER_URL is set
                env = dict(os.environ)
                if 'CELERY_BROKER_URL' not in env:
                    env['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
                
                self.worker_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    env=env
                )
                
                # Stream worker output to logs
                for line in self.worker_process.stdout:
                    if line.strip():
                        log.info("celery.worker.output", message=line.strip())
                        
            except Exception as e:
                log.error("celery.worker.error", error=str(e))
                
            finally:
                # Reset process when worker exits
                self.worker_process = None
                
        self.worker_thread = threading.Thread(target=run_worker, daemon=True)
        self.worker_thread.start()
        
        # Wait for worker to start
        time.sleep(2)
        
    def stop_worker(self):
        """Stop the Celery worker"""
        try:
            if self.worker_process:
                self.worker_process.terminate()
                self.worker_process.wait(timeout=5)
                self.worker_process = None
                log.info("celery.worker.stopped")
        except Exception as e:
            log.error("celery.worker.stop_error", error=str(e))
            
    def is_healthy(self) -> bool:
        """Check if Celery worker is healthy by pinging it (ignore local process)"""
        try:
            current_time = time.time()
            if current_time - self.last_health_check < self.health_check_interval:
                # Don't check too frequently
                return True
            self.last_health_check = current_time
            response = self.control.ping(timeout=1.0)
            is_alive = bool(response)
            if not is_alive:
                log.warning("celery.worker.ping_failed")
            return is_alive
        except Exception as e:
            log.error("celery.worker.health_check_error", error=str(e))
            return False

# Global worker manager instance
worker_manager = CeleryWorkerManager()
