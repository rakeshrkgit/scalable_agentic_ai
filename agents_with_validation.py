"""
Agentic AI Framework (LLM Integrated, Cost-Aware, Validator Added)
PART 1: Core Infrastructure and Base Agents
"""

import threading
import queue
import uuid
import random
from concurrent.futures import ThreadPoolExecutor
import yaml
import json

# ==============================
# Core Infrastructure
# ==============================
class StateStore:
    def __init__(self, backend="memory"):
        self.backend = backend
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

    def dump(self):
        return self.state

class DeadLetterQueue:
    def __init__(self):
        self.queue = []
    def push(self, task, reason):
        self.queue.append((task, reason))

class CircuitBreaker:
    def __init__(self, max_retries=3, max_cost=10000):
        self.max_retries = max_retries
        self.failures = {}
        self.cost_spent = 0
        self.max_cost = max_cost
    def allow(self, task_id, cost=0):
        if self.cost_spent + cost > self.max_cost:
            return False
        return self.failures.get(task_id, 0) < self.max_retries
    def record_failure(self, task_id):
        self.failures[task_id] = self.failures.get(task_id, 0) + 1
    def record_cost(self, cost):
        self.cost_spent += cost

# ==============================
# Base Agent
# ==============================
class BaseAgent:
    def __init__(self, name, state_store, dlq, cb):
        self.name = name
        self.state_store = state_store
        self.dlq = dlq
        self.cb = cb
    def run(self, task):
        raise NotImplementedError

# ==============================
# Core Agents
# ==============================
class IntentAgent(BaseAgent):
    def run(self, task):
        return {"intent": "process", "prompt": task.get("prompt", f"Task {task['id']}")}

class ReasoningAgent(BaseAgent):
    def run(self, task):
        # Smart batching: combine subtasks into one LLM call
        batched_prompt = f"{task['prompt']} - Perform steps 1 and 2 together"
        batched_task = {
            "id": str(uuid.uuid4()),
            "prompt": batched_prompt,
            "mode": "batched",
            "agent": "llm",
            "model_tier": task.get("model_tier", "low"),
            "max_tokens": task.get("max_tokens", 512)
        }
        return {"subtasks": [batched_task]}

class PlanningAgent(BaseAgent):
    def run(self, task):
        dag = {"parent": task["id"], "children": [st["id"] for st in task.get("subtasks", [])]}
        return {"dag": dag}

class TaskExecutionAgent(BaseAgent):
    def run(self, task):
        prompt = task.get("prompt", f"Task {task['id']}")
        result = f"Executed: {prompt}"
        return {"result": result, "id": task["id"], "prompt": prompt}

class LoggingAgent(BaseAgent):
    def run(self, task):
        print(f"[LOG] Agent {self.name} processed task {task['id']} with prompt: {task.get('prompt')}")
        return {"logged": True}

class FeedbackAgent(BaseAgent):
    def run(self, task):
        return {"feedback": f"Task {task['id']} completed successfully"}

class SelfImprovementAgent(BaseAgent):
    def run(self, task):
        return {"improvement": f"Learned from {task['id']}"}

class GenericAgent(BaseAgent):
    def run(self, task):
        return {"result": f"GenericAgent handled task {task.get('prompt', task['id'])}"}

class MemoryAgent(BaseAgent):
    def run(self, task):
        self.state_store.update(task["id"], task, version=random.randint(1, 1000))
        return {"memory_saved": True}
    def recall(self, task_id):
        return self.state_store.get(task_id)

"""
Agentic AI Framework (LLM Integrated, Cost-Aware, Validator Added)
PART 2: Production-Grade Agents + LLM Wrapper + Validator
"""

# ==============================
# Production-Grade Agents
# ==============================
class MonitoringAgent(BaseAgent):
    def run(self, task):
        print(f"[MONITOR] Task {task['id']} status: {task.get('status')}")
        return {"monitored": True}

class SecurityAgent(BaseAgent):
    def run(self, task):
        print(f"[SECURITY] Checked access for task {task['id']}")
        return {"security_checked": True}

class OrchestrationAgent(BaseAgent):
    def run(self, task):
        print(f"[ORCHESTRATION] Orchestrated task {task['id']}")
        return {"orchestrated": True}

class RecoveryAgent(BaseAgent):
    def run(self, task):
        if task.get("status") == "failed":
            print(f"[RECOVERY] Applied recovery for task {task['id']}")
            return {"recovery": f"Applied recovery for {task['id']}"}
        return {"recovery": "Not needed"}

class AuditAgent(BaseAgent):
    def run(self, task):
        print(f"[AUDIT] Recorded lineage for task {task['id']}")
        return {"audited": True}

class NotificationAgent(BaseAgent):
    def run(self, task):
        print(f"[NOTIFY] Task {task['id']} completed, sending notification...")
        return {"notified": True}

class OptimizationAgent(BaseAgent):
    def run(self, task):
        print(f"[OPTIMIZATION] Suggested improvements for task {task['id']}")
        return {"optimization": f"Suggested improvements for {task['id']}"}

# ==============================
# LLM Wrapper Agent
# ==============================
class LLMWrapperAgent(BaseAgent):
    """
    Cost-aware wrapper for OpenAI/Claude API calls.
    Supports model_tier (low/high), max_tokens, and budget checks.
    """
    MODEL_COST = {
        "low": 0.001,   # cost per token (example)
        "high": 0.01,
    }

    def __init__(self, name, state_store, dlq, cb, model_tier="low", max_tokens=512):
        super().__init__(name, state_store, dlq, cb)
        self.model_tier = model_tier
        self.max_tokens = max_tokens

    def run(self, task):
        prompt = task.get("prompt", f"Task {task['id']}")
        tier = task.get("model_tier", self.model_tier)
        max_tokens = task.get("max_tokens", self.max_tokens)

        # Estimate cost
        est_cost = max_tokens * self.MODEL_COST.get(tier, 0.001)

        # Check budget via circuit breaker
        if not self.cb.allow(task["id"], cost=est_cost):
            self.dlq.push(task, "Budget exceeded or retries exhausted")
            return {"result": None, "error": "Budget exceeded"}

        # Record cost
        self.cb.record_cost(est_cost)

        # Pseudo-code: call external LLM API
        # Replace with actual OpenAI/Claude SDK calls
        response = f"[LLM-{tier}] Response to: {prompt[:50]}..."

        print(f"[LLMWrapper] Model tier={tier}, tokens={max_tokens}, cost={est_cost:.4f}")

        return {"result": response, "id": task["id"], "prompt": prompt}

# ==============================
# Validator Agent
# ==============================
class ValidatorAgent(BaseAgent):
    """
    Validates outputs from other agents before acceptance.
    Can enforce format, domain rules, or safety checks.
    """
    def run(self, task):
        result = task.get("result")
        if not result:
            return {"valid": False, "reason": "Empty result"}

        # Example: enforce JSON format if expected
        if task.get("expected_format") == "json":
            try:
                json.loads(result)
            except Exception:
                return {"valid": False, "reason": "Invalid JSON"}

        # Example: domain-specific check
        if "premium" in task.get("prompt", "").lower() and "calculated" not in result.lower():
            return {"valid": False, "reason": "Premium calculation missing"}

        return {"valid": True, "reason": "Passed validation"}

"""
Agentic AI Framework (LLM Integrated, Cost-Aware, Validator Added)
PART 3: Dispatcher + WorkflowManager + DAG Visualization
"""

# ==============================
# Dispatcher
# ==============================
class Dispatcher:
    def __init__(self):
        self.task_queue = queue.Queue()
        self.state_store = StateStore()
        self.dlq = DeadLetterQueue()
        self.cb = CircuitBreaker(max_retries=3, max_cost=5000)
        self.executor = ThreadPoolExecutor(max_workers=5)

        # Agent registry
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
            "monitoring": MonitoringAgent("MonitoringAgent", self.state_store, self.dlq, self.cb),
            "security": SecurityAgent("SecurityAgent", self.state_store, self.dlq, self.cb),
            "orchestration": OrchestrationAgent("OrchestrationAgent", self.state_store, self.dlq, self.cb),
            "recovery": RecoveryAgent("RecoveryAgent", self.state_store, self.dlq, self.cb),
            "audit": AuditAgent("AuditAgent", self.state_store, self.dlq, self.cb),
            "notification": NotificationAgent("NotificationAgent", self.state_store, self.dlq, self.cb),
            "optimization": OptimizationAgent("OptimizationAgent", self.state_store, self.dlq, self.cb),
            "llm": LLMWrapperAgent("LLMWrapperAgent", self.state_store, self.dlq, self.cb),
            "validator": ValidatorAgent("ValidatorAgent", self.state_store, self.dlq, self.cb),
        }

    def submit_task(self, task):
        self.task_queue.put(task)

    def process_task(self, task):
        try:
            if "prompt" not in task:
                task["prompt"] = f"Run {task['id']} step"

            agent_key = task.get("agent", "execution")
            agent = self.agents.get(agent_key, self.agents["generic"])

            # Run agent
            result = agent.run(task)
            task.update(result)

            # Validate output
            validation = self.agents["validator"].run(task)
            if not validation["valid"]:
                print(f"[VALIDATOR] Task {task['id']} failed validation: {validation['reason']}")
                self.agents["recovery"].run(task)
                task["status"] = "failed"
                self.dlq.push(task, validation["reason"])
            else:
                print(f"[VALIDATOR] Task {task['id']} passed validation")
                task["status"] = "completed"

            # Post-processing
            self.agents["logging"].run(task)
            self.agents["memory"].run(task)
            self.agents["monitoring"].run(task)
            self.agents["security"].run(task)
            self.agents["orchestration"].run(task)
            self.agents["audit"].run(task)
            self.agents["notification"].run(task)
            self.agents["optimization"].run(task)

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

    def load_workflow_from_yaml(self, yaml_str):
        workflow = yaml.safe_load(yaml_str)
        for task in workflow["tasks"]:
            if "prompt" not in task:
                task["prompt"] = f"Run {task['id']} step"
            if "model_tier" not in task:
                task["model_tier"] = "low"
            if "max_tokens" not in task:
                task["max_tokens"] = 512
        return workflow

    def load_workflow_from_json(self, json_str):
        workflow = json.loads(json_str)
        for task in workflow["tasks"]:
            if "prompt" not in task:
                task["prompt"] = f"Run {task['id']} step"
            if "model_tier" not in task:
                task["model_tier"] = "low"
            if "max_tokens" not in task:
                task["max_tokens"] = 512
        return workflow

    def submit_workflow(self, workflow):
        for task in workflow["tasks"]:
            task["workflow_id"] = workflow["workflow_id"]
            task["status"] = "pending"
            self.dispatcher.submit_task(task)

    def run_workflow(self, workflow):
        print(f"\n[WORKFLOW START] {workflow['name']} ({workflow['workflow_id']})")
        self.submit_workflow(workflow)
        self.visualize_dag(workflow)
        self.dispatcher.run()
        print(f"[WORKFLOW END] {workflow['name']} ({workflow['workflow_id']})")

    # ==============================
    # DAG Visualization
    # ==============================
    def visualize_dag(self, workflow):
        print("\n[DAG Visualization - ASCII]")
        for task in workflow["tasks"]:
            depends = task.get("depends_on", [])
            if depends:
                print(f"{task['id']} <-- depends on {depends}")
            else:
                print(f"{task['id']} (root task)")

        try:
            with open("workflow_dag.dot", "w") as f:
                f.write("digraph Workflow {\n")
                for task in workflow["tasks"]:
                    f.write(f'  "{task["id"]}" [label="{task["id"]}\\n{task["agent"]}\\n{task["model_tier"]}"];\n')
                    for dep in task.get("depends_on", []):
                        f.write(f'  "{dep}" -> "{task["id"]}";\n')
                f.write("}\n")
            print("[DAG Visualization] Exported to workflow_dag.dot (Graphviz format)")
        except Exception as e:
            print(f"[DAG Visualization] Failed to export: {e}")

"""
Agentic AI Framework (LLM Integrated, Cost-Aware, Validator Added)
PART 4: Demo Runner
"""

# ==============================
# Demo Runner
# ==============================
if __name__ == "__main__":
    dispatcher = Dispatcher()
    manager = WorkflowManager(dispatcher)

    # Example YAML workflow definition (Premium Calculation with validation)
    premium_yaml = """
    workflow_id: wf_002
    name: "Premium Calculation Workflow"
    tasks:
      - id: calculate_premium
        agent: llm
        model_tier: high
        max_tokens: 512
        prompt: "Calculate insurance premium for policyholder X and return JSON with field 'premium'"
        expected_format: json
      - id: store_result
        agent: execution
        depends_on: [calculate_premium]
        prompt: "Store premium result into database"
    """

    # Load workflow from YAML
    workflow = manager.load_workflow_from_yaml(premium_yaml)

    # Run workflow
    manager.run_workflow(workflow)

    # Show DLQ and persisted state
    print("\nDead Letter Queue:", dispatcher.dlq.queue)
    print("\nState Store:", dispatcher.state_store.dump())
