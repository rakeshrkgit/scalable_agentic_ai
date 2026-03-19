"""
Agentic AI Framework with WorkflowManager + MemoryAgent
Auto-generates workflows from initial tasks using DAG orchestration and persists state.
"""

import threading
import queue
import uuid
import random
from concurrent.futures import ThreadPoolExecutor

# ==============================
# Core Infrastructure
# ==============================
class StateStore:
    def __init__(self):
        self.state = {}
        self.lock = threading.Lock()
    def update(self, key, value, version):
        with self.lock:
            current_version = self.state.get(key, {}).get("version", 0)
            if version > current_version:
                self.state[key] = {"value": value, "version": version}
                return True
            return False
    def get(self, key):
        return self.state.get(key, {}).get("value")

class DeadLetterQueue:
    def __init__(self):
        self.queue = []
    def push(self, task, reason):
        self.queue.append((task, reason))

class CircuitBreaker:
    def __init__(self, max_retries=3):
        self.max_retries = max_retries
        self.failures = {}
    def allow(self, task_id):
        return self.failures.get(task_id, 0) < self.max_retries
    def record_failure(self, task_id):
        self.failures[task_id] = self.failures.get(task_id, 0) + 1

# ==============================
# Agents
# ==============================
class BaseAgent:
    def __init__(self, name, state_store, dlq, cb):
        self.name = name
        self.state_store = state_store
        self.dlq = dlq
        self.cb = cb
    def run(self, task):
        raise NotImplementedError

class IntentAgent(BaseAgent):
    def run(self, task):
        return {"intent": "process", "prompt": task["prompt"]}

class ReasoningAgent(BaseAgent):
    def run(self, task):
        subtasks = [
            {"id": str(uuid.uuid4()), "prompt": f"{task['prompt']} - Step 1", "mode": "sequential"},
            {"id": str(uuid.uuid4()), "prompt": f"{task['prompt']} - Step 2", "mode": "parallel"},
            {"id": str(uuid.uuid4()), "prompt": f"{task['prompt']} - Step 3", "mode": "parallel"},
        ]
        return {"subtasks": subtasks}

class PlanningAgent(BaseAgent):
    def run(self, task):
        dag = {"parent": task["id"], "children": [st["id"] for st in task["subtasks"]]}
        return {"dag": dag}

class TaskExecutionAgent(BaseAgent):
    def run(self, task):
        result = f"Executed: {task['prompt']}"
        return {"result": result, "id": task["id"], "prompt": task["prompt"]}

class LoggingAgent(BaseAgent):
    def run(self, task):
        print(f"[LOG] Agent {self.name} processed task {task['id']} with prompt: {task['prompt']}")
        return {"logged": True}

class FeedbackAgent(BaseAgent):
    def run(self, task):
        return {"feedback": f"Task {task['id']} completed successfully"}

class SelfImprovementAgent(BaseAgent):
    def run(self, task):
        return {"improvement": f"Learned from {task['id']}"}

class GenericAgent(BaseAgent):
    def run(self, task):
        return {
            "id": task.get("id", str(uuid.uuid4())),
            "prompt": task.get("prompt", "Unknown task"),
            "result": f"GenericAgent handled task with prompt: {task.get('prompt')}"
        }

class MemoryAgent(BaseAgent):
    def run(self, task):
        # Persist task state
        self.state_store.update(task["id"], task, version=random.randint(1, 1000))
        return {"memory_saved": True}
    def recall(self, task_id):
        return self.state_store.get(task_id)

# ==============================
# Dispatcher
# ==============================
class Dispatcher:
    def __init__(self):
        self.task_queue = queue.Queue()
        self.state_store = StateStore()
        self.dlq = DeadLetterQueue()
        self.cb = CircuitBreaker()
        self.executor = ThreadPoolExecutor(max_workers=5)

        self.agents = {
            "intent": IntentAgent("IntentAgent", self.state_store, self.dlq, self.cb),
            "reasoning": ReasoningAgent("ReasoningAgent", self.state_store, self.dlq, self.cb),
            "planning": PlanningAgent("PlanningAgent", self.state_store, self.dlq, self.cb),
            "execution": TaskExecutionAgent("TaskExecutionAgent", self.state_store, self.dlq, self.cb),
            "logging": LoggingAgent("LoggingAgent", self.state_store, self.dlq, self.cb),
            "feedback": FeedbackAgent("FeedbackAgent", self.state_store, self.dlq, self.cb),
            "self_improvement": SelfImprovementAgent("SelfImprovementAgent", self.state_store, self.dlq, self.cb),
            "generic": GenericAgent("GenericAgent", self.state_store, self.dlq, self.cb),
            "memory": MemoryAgent("MemoryAgent", self.state_store, self.dlq, self.cb),
        }

    def submit_task(self, task):
        self.task_queue.put(task)

    def process_task(self, task):
        try:
            if not self.cb.allow(task["id"]):
                self.dlq.push(task, "Circuit breaker triggered")
                return

            # Intent
            intent_out = self.agents["intent"].run(task)
            task.update(intent_out)
            self.agents["memory"].run(task)

            # Reasoning
            reasoning_out = self.agents["reasoning"].run(task)
            task.update(reasoning_out)
            self.agents["memory"].run(task)

            # Planning
            planning_out = self.agents["planning"].run(task)
            task.update(planning_out)
            self.agents["memory"].run(task)

            # Execution
            execution_results = []
            for st in [s for s in task["subtasks"] if s["mode"] == "sequential"]:
                res = self.agents["execution"].run(st)
                execution_results.append(res)
                self.agents["memory"].run(res)
            futures = []
            for st in [s for s in task["subtasks"] if s["mode"] == "parallel"]:
                futures.append(self.executor.submit(self.agents["execution"].run, st))
            for f in futures:
                res = f.result()
                execution_results.append(res)
                self.agents["memory"].run(res)
            task["execution"] = execution_results

            if all(res.get("result") for res in execution_results):
                task["status"] = "completed"
            else:
                task["status"] = "failed"

            self.agents["logging"].run(task)
            feedback_out = self.agents["feedback"].run(task)
            task.update(feedback_out)
            self.agents["memory"].run(task)

            improvement_out = self.agents["self_improvement"].run(task)
            task.update(improvement_out)
            self.agents["memory"].run(task)

            return task

        except Exception as e:
            self.cb.record_failure(task["id"])
            self.dlq.push(task, str(e))
            task["status"] = "failed"

    def run(self):
        while not self.task_queue.empty():
            task = self.task_queue.get()
            result = self.process_task(task)
            print(f"[RESULT] {result}")

# ==============================
# Workflow Manager
# ==============================
class WorkflowManager:
    def __init__(self, dispatcher):
        self.dispatcher = dispatcher

    def generate_workflow(self, prompt):
        workflow_id = str(uuid.uuid4())
        workflow = {
            "workflow_id": workflow_id,
            "name": f"Workflow for {prompt}",
            "tasks": []
        }
        parent_task = {"id": str(uuid.uuid4()), "prompt": prompt, "workflow_id": workflow_id, "status": "pending"}
        workflow["tasks"].append(parent_task)
        return workflow

    def submit_workflow(self, workflow):
        for task in workflow["tasks"]:
            self.dispatcher.submit_task(task)

    def run_workflow(self, workflow):
        print(f"\n[WORKFLOW START] {workflow['name']} ({workflow['workflow_id']})")
        self.submit_workflow(workflow)
        self.dispatcher.run()
        print(f"[WORKFLOW END] {workflow['name']} ({workflow['workflow_id']})")

# ==============================
# Demo
# ==============================
if __name__ == "__main__":
    dispatcher = Dispatcher()
    manager = WorkflowManager(dispatcher)

    workflow = manager.generate_workflow("Build a customer churn prediction model")
    manager.run_workflow(workflow)

    print("\nDead Letter Queue:", dispatcher.dlq.queue)
    print("\nState Store:", dispatcher.state_store.state)
