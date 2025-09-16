# -*- coding:utf-8 -*-
import sys
import json
import os
import copy

def extract_one(result_file):
    freq = []
    init_answer = None
    with open(result_file, 'r', encoding='utf-8') as ifs:
        for line in ifs:
            obj = json.loads(line)
            call_reason = obj['call_reason']
            text = obj['text']
            stop_reason = obj['finish_reason']
            if stop_reason != 'stop':
                continue
            if call_reason == 'step1':
                init_answer = text
            if call_reason in ["step1", "step2_refine", "correction"]:
                freq.append([text, 0])
            elif call_reason in ["verify_solution"] and len(freq) > 0:
                freq[-1][1] += 1
    if len(freq) == 0:
        print(result_file)
        return None, None, None

    vec = sorted(freq, key=lambda x: x[1], reverse=True)
    return vec[0][0], vec[0][1], init_answer


def extract_all(test_file, input_dir):
    with open(test_file, 'r', encoding='utf-8') as ifs:
        obj_list = [json.loads(line) for line in ifs]
    data_count = len(obj_list)
    init_answer_list, eval_v1_list, eval_v2_list = [], [], []
    for obj in obj_list:
        init_answer_list.append(copy.deepcopy(obj))
        eval_v1_list.append(copy.deepcopy(obj))
        eval_v2_list.append(copy.deepcopy(obj))
    
    init_ofs = open(f"{input_dir}/init_answer.jsonl", 'w', encoding='utf-8')
    v1_ofs = open(f"{input_dir}/eval_accepted.jsonl", 'w', encoding='utf-8')
    v2_ofs = open(f"{input_dir}/eval_overall.jsonl", 'w', encoding='utf-8')
    for idx in range(data_count):
        for n_t in range(16):
            if n_t == 0:
                for xlist in [init_answer_list, eval_v2_list, eval_v1_list]:
                    xlist[idx]["solution"] = []
                    xlist[idx]["solution_freq"] = []
            fname = f"{input_dir}/{idx}.json.{n_t}"
            if os.path.exists(fname) is False: continue
            solution, freq, init_answer = extract_one(fname)
            if solution is None:
                solution = 'Solve Failed'
                freq = 0
            init_answer_list[idx]["solution"].append(init_answer)
            init_answer_list[idx]["solution_freq"].append(1)
            eval_v2_list[idx]["solution"].append(solution)
            eval_v2_list[idx]["solution_freq"].append(freq)
            if freq >= 3:
                eval_v1_list[idx]["solution"].append(solution)
                eval_v1_list[idx]["solution_freq"].append(freq)

        if len(init_answer_list[idx]["solution"]) > 0:
            init_ofs.write(json.dumps(init_answer_list[idx], ensure_ascii=False) + '\n')
        if len(eval_v1_list[idx]["solution"]) > 0:
            v1_ofs.write(json.dumps(eval_v1_list[idx], ensure_ascii=False) + '\n')
        if len(eval_v2_list[idx]["solution"]) > 0:
            v2_ofs.write(json.dumps(eval_v2_list[idx], ensure_ascii=False) + '\n')
    init_ofs.close()
    v1_ofs.close()
    v2_ofs.close()

if __name__ == "__main__":
    input_dir = sys.argv[1]
    test_file = sys.argv[2]
    extract_all(test_file, input_dir)

