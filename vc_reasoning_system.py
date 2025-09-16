# -*- coding:utf-8 -*-
import time
from datetime import datetime
import json
import multiprocessing
from enum import Enum
import threading
import sys
import os
import pathlib
sys.path.append(str(pathlib.Path(__file__).parent))
from llm_client import call_llm
from prompts import step1_prompt, self_improvement_prompt, correction_prompt, verification_system_prompt, verification_remider

SOLVER_IP_LIST = []
VC_IP_LIST = []

class AgentStatusCode(Enum):
    OK = 0
    Init = 1
    Error = 2
    ForceToExit = 3


class Agent(object):

    def __init__(self):
        self.lock = threading.Lock()
        self.ofs_dict = {}
        self.log_dict = {}
        self.status_code_dict = {}
        self.llm_calls_dict = {}

    def init(self, output_file, log_file, worker_id):
        self.lock.acquire()
        thread_id = threading.current_thread().ident
        self.ofs_dict[thread_id] = open(f"{output_file}.{worker_id}", "w", encoding='utf-8')
        self.log_dict[thread_id] = open(f"{log_file}.{worker_id}", "w", encoding='utf-8')
        self.status_code_dict[thread_id] = AgentStatusCode.Init
        self.llm_calls_dict[thread_id] = []
        self.lock.release()

    def _call_llm(self, messages, call_reason):
        if 'step1' in call_reason:
            ip_list = SOLVER_IP_LIST
        else:
            ip_list = VC_IP_LIST
        vllm_obj = call_llm(messages, ip_list)
        vllm_obj["call_reason"] = call_reason
        thread_id = threading.current_thread().ident
        self.llm_calls_dict[thread_id].append(vllm_obj)
        self.ofs_dict[thread_id].write(json.dumps(vllm_obj, ensure_ascii=False) + '\n')
        self.ofs_dict[thread_id].flush()
        return vllm_obj["text"].split("</think>")[-1], vllm_obj["finish_reason"]

    def log(self, msg):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        thread_id = threading.current_thread().ident
        self.log_dict[thread_id].write(f"[{ts}]{msg}\n")
        self.log_dict[thread_id].flush()

    @staticmethod
    def extract_detailed_solution(solution, marker='Detailed Solution', after=True):
        idx = solution.find(marker)
        if idx == -1:
            return ''
        if after:
            return solution[idx + len(marker):].strip()
        else:
            return solution[:idx].strip()

    def verify_solution(self, problem_statement, solution):
        self.log(f"[verify_solution] begin.")
        dsol = solution

        newst = f"""
======================================================================
### Problem ###

{problem_statement}

======================================================================
### Solution ###

{dsol}

{verification_remider}
"""

        self.log(f"[verify_solution] call_vllm_verification begin: {[newst]}")
        verification_result, finish_reason = self._call_llm([
            {"role": "system", "content": [verification_system_prompt]},
            {"role": "user", "content": [newst]}
        ], "verify_solution")
        self.log(f"[verify_solution] call_vllm_verification end: {[verification_result]}")

        bug_report = ""
        check_correctness_result = verification_result.lower().split('correctness')[-1]
        if "correct" not in check_correctness_result:
            bug_report = Agent.extract_detailed_solution(verification_result, "**Correctness**", False)

        self.log(f"[verify_solution] end. bug_report: {[bug_report]}, final_result: {[check_correctness_result]}")
        return bug_report, check_correctness_result

    def init_explorations(self, problem_statement):
        self.log(f"[init_explorations] begin. problem: {[problem_statement]}")
        self.log(f"[init_explorations] call_llm with step1_prompt:")
        n_try = 3
        while n_try > 0:
            n_try -= 1
            step1_solution, finish_reason = self._call_llm([
              {"role": "user", "content": [problem_statement]}
            ], "step1")
            self.log(f"[init_explorations] step1_init result: {[step1_solution]}")
            is_complete = True if finish_reason == "stop" else False
            if is_complete is True:
                break
        if is_complete is False:
            self.log(f"[init_explorations] is_complete: {[is_complete]}, exit")
            return None
        self.log(f"[init_explorations] is_complete: {[is_complete]}")
        return step1_solution

    def _run_one_worker(self, problem_statement, output_file, log_file, worker_id):
        self.init(output_file, log_file, worker_id)
        self.log(f"[agent][{worker_id}] begin. problem: {[problem_statement]}")
        solution = self.init_explorations(problem_statement)
        if solution is None:
            self.log(f"[agent][{worker_id}] solution is None, exit.")
            return None

        bug_report, check_correctness_result = self.verify_solution(problem_statement, solution)
        error_count = 0
        correct_count = 1
        for i in range(10):
            self.log(f"[agent][{worker_id}] Number of iterations: {i}, {correct_count=}, {error_count=}")
            if "correct" not in check_correctness_result.lower():
                correct_count = 0
                error_count += 1
                self.log(f"[agent][{worker_id}] correct not found. need correction.")
                self.log(f"[agent][{worker_id}] call llm with correction_prompt")
                prev_solution = solution
                solution, finish_reason = self._call_llm([
                    {"role": "user", "content": [problem_statement]},
                    {"role": "model", "content": [prev_solution]},
                    {"role": "user", "content": [correction_prompt, bug_report]}
                ], "correction")
                is_complete = True if finish_reason == "stop" else False
                self.log(f"[agent][{worker_id}] refine_result: {[solution]}, is_complete: {[is_complete]}")
                if not is_complete:
                    self.log(f"[agent][{worker_id}] is_complete is False, exit")
                    return None
            self.log(f"[agent][{worker_id}] verify_solution begin.")
            bug_report, check_correctness_result = self.verify_solution(problem_statement, solution)
            self.log(f"[agent][{worker_id}] verify_solution end. bug_report: {[bug_report]}, check_correctness_result: {[check_correctness_result]}")
            if "correct" in check_correctness_result.lower():
                self.log(f"[agent][{worker_id}] Solution is good, verifying again ...")
                correct_count += 1
                error_count = 0
            if correct_count >= 4:
                self.log(f"[agent][{worker_id}] Correct solution found.")
                self.log(f"[agent][{worker_id}] --------------------")
                self.log(f"####FINAL SOLUTION#### {solution}")
                return solution
            elif error_count >= 10:
                break
        self.log(f"[agent][{worker_id}] Failed in finding a correct solution.")
        return None

    def run_one_worker(self, problem_statement, output_file, log_file, worker_id):
        solution = self._run_one_worker(problem_statement, output_file, log_file, worker_id)


def run_all_workers(problem_statement, output_file, log_file, worker_count):
    agent = Agent()
    workers = []
    for worker_id in range(worker_count):
        worker = threading.Thread(target=agent.run_one_worker, args=(problem_statement, output_file, log_file, worker_id,))
        workers.append(worker)
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()


def process_all(input_file, output_dir):
    with open(input_file, 'r', encoding='utf-8') as ifs:
        obj_list = [json.loads(line) for line in ifs]

    workers = []
    for idx, obj in enumerate(obj_list):
        output_file = f"{output_dir}/{idx}.json"
        log_file = f"{output_dir}/{idx}_log.json"
        p = multiprocessing.Process(target=run_all_workers, args=(obj["query"], output_file, log_file, 1,))
        workers.append(p)
    for p in workers:
        p.start()
    for p in workers:
        p.join()


if __name__ == "__main__":
    solver_info = sys.argv[1]
    vc_info = sys.argv[2]
    input_file = sys.argv[3]
    output_dir = sys.argv[4]

    for ip_port in solver_info.strip().split(','):
        if ip_port.strip():
            SOLVER_IP_LIST.append(ip_port)

    for ip_port in vc_info.strip().split(','):
        if ip_port.strip():
            VC_IP_LIST.append(ip_port)

    try:
        os.mkdir(output_dir)
    except:
        pass
    process_all(input_file, output_dir)
